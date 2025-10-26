import json
import base64
import boto3
import os
import uuid
import datetime

# --- 1. ดึงชื่อ Table และ Bucket ---

DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME'].strip()
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']

# --- khởi tạo AWS Clients (Region us-east-1) ---
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')
table = dynamodb.Table(DYNAMODB_TABLE_NAME) # 👈 นี่ควรจะเป็น 'lost_items'

# --- Headers สำหรับ CORS ---
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
}

def lambda_handler(event, context):
    
    # --- 1. จัดการ CORS (เหมือนเดิม) ---
    if event['requestContext']['http']['method'] == 'OPTIONS':
        return {'statusCode': 204, 'headers': CORS_HEADERS, 'body': ''}
        
    # --- 2. Parse ข้อมูล (เหมือนเดิม) ---
    try:
        body = json.loads(event['body'])
        
        # (ดึงค่าจาก JS - Field names ตรงกันเป๊ะ ดีมากครับ)
        item_description = body.get('itemDescription') 
        brand_or_id = body.get('brandOrId')           
        features = body.get('distinguishingFeatures') 
        lost_location = body.get('lostLocation')      
        lost_date = body.get('lostDate')              
        lost_time = body.get('lostTime')              
        image_base64 = body.get('imageBase64')        
        reporter_name = body.get('reporterName')      
        reporter_contact = body.get('reporterContact')  
        reporter_student_id = body.get('reporterStudentId') 
        
        # ตรวจสอบฟิลด์ที่จำเป็น (เหมือนเดิม)
        if not all([item_description, lost_location, lost_date, reporter_name, reporter_contact]):
            raise ValueError("Missing required fields")

    except Exception as e:
        print(f"Error parsing input: {e}")
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': f'Invalid input data. {str(e)}'})}

    # --- 3. อัปโหลดรูปภาพไปยัง S3 (ถ้ามี) ---
    s3_url = None 
    
    if image_base64: 
        try:
            header, encoded_data = image_base64.split(',', 1)
            
            # --- ( ⬇️ 3 บรรทัดที่เพิ่มเข้ามา ⬇️ ) ---
            # ✅ (ใหม่!) แก้ปัญหา Incorrect padding
            missing_padding = len(encoded_data) % 4
            if missing_padding != 0:
                encoded_data += '=' * (4 - missing_padding)
            # --- ( ⬆️ จบส่วนที่เพิ่ม ⬆️ ) ---
            
            image_data = base64.b64decode(encoded_data)
            file_extension = header.split(';')[0].split('/')[1]
            content_type = f'image/{file_extension}'
            
            file_name = f"{uuid.uuid4()}.{file_extension}"
            s3_key = f"lost-reports/{lost_date}/{file_name}" 
            
            s3.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=image_data,
                ContentType=content_type
            )
            s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

        except Exception as e:
            print(f"Error uploading to S3: {e}")
            s3_url = None 

    # --- 4. บันทึกข้อมูลทั้งหมดลง DynamoDB (ตาราง lost_items) ---
    try:
        item_id = str(uuid.uuid4())
        # ✅ (ใหม่!) เปลี่ยนเป็น 6 ตัวท้าย ให้เหมือนกับ 'Found'
        case_id = item_id[-6:].upper() 
        timestamp = datetime.datetime.utcnow().isoformat()
        
        item_to_save = {
            'item_id': item_id,             
            'case_id': case_id,             
            'item_type': 'LOST_REPORT', # 👈 นี่คือหัวใจของ Single Table Design
            
            'itemDescription': item_description,
            'lostLocation': lost_location,
            'lostDate': lost_date,
            'reporterName': reporter_name,
            'reporterContact': reporter_contact,
            'reportTimestamp': timestamp,
            'status': 'lost_reported', 
        }
        
        # (เพิ่มฟิลด์ Optional ... เหมือนเดิม)
        if brand_or_id:
            item_to_save['brandOrId'] = brand_or_id
        if features:
            item_to_save['distinguishingFeatures'] = features
        if lost_time:
            item_to_save['lostTime'] = lost_time
        if reporter_student_id:
            item_to_save['reporterStudentId'] = reporter_student_id
        if s3_url: 
            item_to_save['imageUrl'] = s3_url
            
        # บันทึกลง Table 'lost_items' (ถ้าคุณแก้ Env Var ถูกต้อง)
        table.put_item(Item=item_to_save)
        
    except Exception as e:
        print(f"Error writing to DynamoDB: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Failed to write data to DynamoDB'})}

    # --- 5. ส่งคำตอบกลับไปหาฟอร์ม (เหมือนเดิม) ---
    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'status': 'success',
            'message': 'Your lost item report has been submitted.',
            'caseId': case_id # 👈 JavaScript ของคุณรอรับ 'caseId' นี้
        })
    }