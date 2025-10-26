import json
import base64
import boto3
import os
import uuid
import datetime

# --- 1. ดึงชื่อ Table และ Bucket ---

DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']

# --- khởi tạo AWS Clients ---
s3 = boto3.client('s3', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# --- Headers สำหรับ CORS ---
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
}

def lambda_handler(event, context):
    
    # --- 1. จัดการ CORS ---
    if event['requestContext']['http']['method'] == 'OPTIONS':
        return {'statusCode': 204, 'headers': CORS_HEADERS, 'body': ''}
        
    # --- 2. Parse ข้อมูล ---
    try:
        body = json.loads(event['body'])
        
        category = body.get('category')
        brand_name = body.get('brandName')
        item_id_number = body.get('itemIdNumber')
        details = body.get('details')
        found_location = body.get('foundLocation')
        found_date = body.get('foundDate')
        found_time = body.get('foundTime')
        reporter_name = body.get('reporterName')
        reporter_contact = body.get('reporterContact')
        reporter_student_id = body.get('reporterStudentId')
        image_base64 = body.get('imageBase64') # ถ้าไม่มี จะเป็น None
        liff_user_id = body.get('liffUserId', 'unknown_reporter') 
        
        # ✅ แก้ไข: เอา image_base64 ออกจากการตรวจสอบฟิลด์ที่จำเป็น
        if not all([category, found_location, reporter_name, reporter_contact]):
            raise ValueError("Missing required fields (category, location, name, contact)")

    except Exception as e:
        print(f"Error parsing input: {e}")
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': f'Invalid input data. {str(e)}'})}

    # ✅ แก้ไข: กำหนด s3_url เป็น None ก่อน
    s3_url = None

    # --- 3. อัปโหลดรูปภาพไปยัง S3 (ถ้ามี) ---
    # ✅ แก้ไข: ตรวจสอบก่อนว่ามี image_base64 ส่งมาหรือไม่
    if image_base64:
        try:
            header, encoded_data = image_base64.split(',', 1)
            
            missing_padding = len(encoded_data) % 4
            if missing_padding != 0:
                encoded_data += '=' * (4 - missing_padding)
                
            image_data = base64.b64decode(encoded_data)
            file_extension = header.split(';')[0].split('/')[1]
            content_type = f'image/{file_extension}'
            
            file_name = f"{uuid.uuid4()}.{file_extension}"
            s3_key = f"found-items/{category}/{found_date}/{file_name}" 
            
            s3.put_object(
                Bucket=S3_BUCKET_NAME, Key=s3_key,
                Body=image_data, ContentType=content_type
            )
            # ✅ แก้ไข: กำหนดค่า s3_url เมื่ออัปโหลดสำเร็จ
            s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

        except Exception as e:
            print(f"Error uploading to S3: {e}")
            # ถ้าอัปโหลดรูปล้มเหลว (เช่น base64 ผิด) ก็คืน error ไปเลย
            return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': f'Failed to upload image to S3: {str(e)}'})}
    
    # --- 4. บันทึกข้อมูลทั้งหมดลง DynamoDB ---
    try:
        item_id = str(uuid.uuid4()) 
        timestamp = datetime.datetime.utcnow().isoformat()
        human_readable_id = item_id[-6:].upper()
        
        item_to_save = {
            'item_id': item_id,
            'case_id': human_readable_id,
            'item_type': 'FOUND_ITEM',

            'category': category,
            'foundLocation': found_location,
            'foundDate': found_date,
            # ✅ แก้ไข: เอา 'imageUrl' ออกจากตรงนี้
            'reporterName': reporter_name,
            'reporterContact': reporter_contact,
            'reportTimestamp': timestamp,
            'status': 'found_reported', 
            'reporterLiffUserId': liff_user_id
        }
        
        # (เพิ่มฟิลด์ Optional)
        if brand_name:
            item_to_save['brandName'] = brand_name
        if item_id_number:
            item_to_save['itemIdNumber'] = item_id_number
        if details:
            item_to_save['details'] = details
        if found_time:
            item_to_save['foundTime'] = found_time
        if reporter_student_id:
            item_to_save['reporterStudentId'] = reporter_student_id
            
        # ✅ แก้ไข: เพิ่ม imageUrl เข้าไป "เฉพาะในกรณีที่อัปโหลดสำเร็จ" (s3_url ไม่ใช่ None)
        if s3_url:
            item_to_save['imageUrl'] = s3_url
            
        # บันทึกลง Table
        table.put_item(Item=item_to_save)
        
    except Exception as e:
        print(f"Error writing to DynamoDB: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Failed to write data to DynamoDB'})}

    # --- 5. ส่งคำตอบกลับไปหา LIFF ---
    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'status': 'success',
            'itemId': item_id,
            'caseId': human_readable_id 
        })
    }