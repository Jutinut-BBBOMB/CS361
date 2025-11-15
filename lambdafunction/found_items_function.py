import json
import base64
import boto3
import os
import uuid
import datetime
import secrets

DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'Items_TU')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'tu-lostfound-pictures')

s3 = boto3.client('s3', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
}

def lambda_handler(event, context):
    print(f"[DEBUG] Event: {json.dumps(event)}")
    # ---- CORS Preflight ----
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'status': 'ok'})
        }
    try:
        body = json.loads(event.get('body', '{}'))
        action = body.get('action')

        # -------- Upload image --------
        if action == 'upload_image':
            try:
                image_data = body.get('image_data')
                image_name = body.get('image_name', f'{uuid.uuid4()}.jpg')
                folder = body.get('folder', 'found')
                if not image_data:
                    return {
                        'statusCode': 400,
                        'headers': CORS_HEADERS,
                        'body': json.dumps({'status': 'error', 'error': 'Missing image_data'})
                    }
                image_bytes = base64.b64decode(image_data)
                date_str = datetime.datetime.now().strftime('%Y-%m-%d')
                s3_key = f"{folder}/{date_str}/{image_name}"
                s3.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=s3_key,
                    Body=image_bytes,
                    ContentType='image/jpeg'
                )
                image_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
                print(f"[SUCCESS] Image uploaded: {image_url}")
                return {
                    'statusCode': 200,
                    'headers': CORS_HEADERS,
                    'body': json.dumps({'status': 'success', 'image_url': image_url})
                }
            except Exception as e:
                print(f"[ERROR] Image upload failed: {e}")
                return {
                    'statusCode': 500,
                    'headers': CORS_HEADERS,
                    'body': json.dumps({'status': 'error', 'error': str(e)})
                }
        # -------- Report found --------
        elif action == "report_found":
            category = body.get('category')
            brand = body.get('brand') or body.get('brandName', '')
            details = body.get('details', '')
            location = body.get('location') or body.get('foundLocation')
            date = body.get('date') or body.get('foundDate')
            time = body.get('time') or body.get('foundTime', '')
            reporter_name = body.get('reporter_name') or body.get('reporterName')
            reporter_contact = body.get('reporter_contact') or body.get('reporterContact')
            reporter_student_id = body.get('reporter_student_id') or body.get('reporterStudentId', '')
            image_url = body.get('image_url')
            # --- Validation
            for var,val in [('category',category),('location',location),('date',date),('reporter_name',reporter_name),('reporter_contact',reporter_contact)]:
                if not val:
                    return {
                        'statusCode': 400,
                        'headers': CORS_HEADERS,
                        'body': json.dumps({'status': 'error', 'error': f"Missing required: {var}"})
                    }
            # --- Save to DynamoDB
            try:
                item_id = f"ITEM#{int(datetime.datetime.now().timestamp())}-{secrets.token_hex(4)}"
                case_id = f"F{secrets.randbelow(900000) + 100000}"
                timestamp = datetime.datetime.utcnow().isoformat()
                item = {
                    'item_id': item_id,
                    'item_type': 'FOUND',
                    'case_id': case_id,
                    'category': category,
                    'brand': brand,
                    'details': details,
                    'location': location,
                    'date': date,
                    'time': time,
                    'status': 'รอรับคืน',
                    'reporter_name': reporter_name,
                    'reporter_contact': reporter_contact,
                    'reporter_student_id': reporter_student_id,
                    'created_at': timestamp,
                    'updated_at': timestamp,
                    'gsi1_pk': 'STATUS#รอรับคืน',
                    'gsi1_sk': timestamp,
                    'gsi2_pk': f'CATEGORY#{category}',
                    'gsi2_sk': timestamp
                }
                if image_url:
                    item['image_url'] = image_url
                table.put_item(Item=item)
                print(f"[SUCCESS] Item saved: {case_id}")
                return {
                    'statusCode': 200,
                    'headers': CORS_HEADERS,
                    'body': json.dumps({'status': 'success', 'case_id': case_id})
                }
            except Exception as e:
                print(f"[ERROR] DynamoDB error: {e}")
                return {
                    'statusCode': 500,
                    'headers': CORS_HEADERS,
                    'body': json.dumps({'status': 'error', 'error': 'Failed to save data'})
                }

        # ------- Not supported -------
        else:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'status': 'error', 'error': f'Invalid action: {action}'})
            }
    except Exception as e:
        print(f"[ERROR] Handler error: {e}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'status': 'error', 'error': str(e)})
        }
