import json
import base64
import boto3
import os
import uuid
import datetime
import secrets

DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'Items_TU')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'tu-lostfound-pictures')

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
}

def lambda_handler(event, context):
    if event['requestContext']['http']['method'] == 'OPTIONS':
        return {'statusCode': 204, 'headers': CORS_HEADERS, 'body': ''}
    
    try:
        body = json.loads(event['body'])
        
        # รับข้อมูลจากฟอร์ม
        category = body.get('itemDescription', '')  # แมปจาก itemDescription -> category
        brand = body.get('brandOrId', '')  # แมปจาก brandOrId -> brand
        details = body.get('distinguishingFeatures', '')  # แมปจาก distinguishingFeatures -> details
        location = body.get('lostLocation')  # แมปจาก lostLocation -> location
        date = body.get('lostDate')  # แมปจาก lostDate -> date
        time = body.get('lostTime', '')  # แมปจาก lostTime -> time
        reporter_name = body.get('reporterName')
        reporter_contact = body.get('reporterContact')
        reporter_student_id = body.get('reporterStudentId', '')
        image_base64 = body.get('imageBase64', '')
        
        # Validate
        if not all([category, location, date, reporter_name, reporter_contact]):
            raise ValueError("Missing required fields")
            
    except Exception as e:
        print(f"Error parsing input: {e}")
        return {
            'statusCode': 400,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': f'Invalid input: {str(e)}'})
        }
    
    # อัปโหลดรูปภาพ
    image_url = None
    if image_base64:
        try:
            header, encoded_data = image_base64.split(',', 1)
            missing_padding = len(encoded_data) % 4
            if missing_padding:
                encoded_data += '=' * (4 - missing_padding)
            
            image_data = base64.b64decode(encoded_data)
            file_ext = header.split(';')[0].split('/')[1]
            file_name = f"{uuid.uuid4()}.{file_ext}"
            s3_key = f"lost/{date}/{file_name}"
            
            s3.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=image_data,
                ContentType=f'image/{file_ext}'
            )
            image_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
        except Exception as e:
            print(f"Image upload error: {e}")
    
    # บันทึกลง DynamoDB
    try:
        item_id = f"ITEM#{int(datetime.datetime.now().timestamp())}-{secrets.token_hex(4)}"
        case_id = f"L{secrets.randbelow(900000) + 100000}"
        timestamp = datetime.datetime.utcnow().isoformat()
        
        item = {
            'item_id': item_id,
            'item_type': 'LOST',
            'case_id': case_id,
            'category': category,
            'brand': brand,
            'details': details,
            'location': location,
            'date': date,
            'time': time,
            'status': 'แจ้งแล้ว',
            'reporter_name': reporter_name,
            'reporter_contact': reporter_contact,
            'reporter_student_id': reporter_student_id,
            'created_at': timestamp,
            'updated_at': timestamp,
            'gsi1_pk': 'STATUS#แจ้งแล้ว',
            'gsi1_sk': timestamp,
            'gsi2_pk': f'CATEGORY#{category}',
            'gsi2_sk': timestamp
        }
        
        if image_url:
            item['image_url'] = image_url
        
        table.put_item(Item=item)
        
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'success',
                'caseId': case_id,
                'message': 'Lost item reported successfully'
            })
        }
        
    except Exception as e:
        print(f"DynamoDB error: {e}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Failed to save data'})
        }


