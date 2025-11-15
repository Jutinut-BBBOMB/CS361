import json
import boto3
import re
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
table = dynamodb.Table('Items_TU')

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json'
}

def lambda_handler(event, context):
    try:
        print(f"[DEBUG] Event: {json.dumps(event)}")
        
        # Handle OPTIONS
        http_method = event.get('requestContext', {}).get('http', {}).get('method', '')
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': CORS_HEADERS,
                'body': json.dumps({'status': 'ok'})
            }
        
        # Parse body
        body_raw = event.get('body', '{}')
        if isinstance(body_raw, str):
            body = json.loads(body_raw)
        else:
            body = body_raw
        
        action = body.get('action')
        item_id = body.get('item_id')
        
        print(f"[DEBUG] Action: {action}, Item ID: {item_id}")
        
        if not item_id:
            return error_response('Missing item_id', 400)
        
        # ⚠️ สำคัญ: ต้องหา item_type (Sort Key) ก่อน
        # ใช้ Query เพื่อหา item
        response = table.query(
            KeyConditionExpression='item_id = :item_id',
            ExpressionAttributeValues={
                ':item_id': item_id
            },
            Limit=1
        )
        
        items = response.get('Items', [])
        if not items:
            return error_response('Item not found', 404)
        
        item = items[0]
        item_type = item.get('item_type')  # LOST หรือ FOUND
        
        print(f"[DEBUG] Found item_type: {item_type}")
        
        # สร้าง Key สำหรับ DynamoDB (ต้องมีทั้ง Partition และ Sort Key)
        key = {
            'item_id': item_id,
            'item_type': item_type
        }
        
        # ✅ ACTION: DELETE
        if action == 'delete':
            # ลบรูปภาพ S3
            image_url = item.get('image_url')
            if image_url:
                try:
                    match = re.search(r'amazonaws\.com/(.+)$', image_url)
                    if match:
                        s3_key = match.group(1)
                        s3.delete_object(Bucket='tu-lostfound-pictures', Key=s3_key)
                        print(f"[SUCCESS] Deleted S3: {s3_key}")
                except Exception as s3_err:
                    print(f"[WARN] S3 delete failed: {s3_err}")
            
            # ลบจาก DynamoDB
            table.delete_item(Key=key)
            print(f"[SUCCESS] Deleted item: {item_id} ({item_type})")
            
            return success_response('ลบรายการสำเร็จ')
        
        # ✅ ACTION: CHANGE_STATUS
        elif action == 'change_status':
            new_status = body.get('status')
            valid_statuses = ['แจ้งแล้ว', 'รอรับคืน', 'คืนเจ้าของแล้ว', 'หมดอายุ']
            
            if not new_status or new_status not in valid_statuses:
                return error_response(f'Invalid status: {new_status}', 400)
            
            # อัปเดตสถานะ
            table.update_item(
                Key=key,
                UpdateExpression='SET #status = :status, #updated_at = :updated_at, #gsi1_pk = :gsi1_pk',
                ExpressionAttributeNames={
                    '#status': 'status',
                    '#updated_at': 'updated_at',
                    '#gsi1_pk': 'gsi1_pk'
                },
                ExpressionAttributeValues={
                    ':status': new_status,
                    ':updated_at': datetime.utcnow().isoformat(),
                    ':gsi1_pk': f'STATUS#{new_status}'
                }
            )
            
            print(f"[SUCCESS] Changed status to: {new_status}")
            return success_response(f'เปลี่ยนสถานะเป็น "{new_status}" สำเร็จ')
        
        # ✅ ACTION: UPDATE
        elif action == 'update':
            updates = body.get('updates', {})
            if not updates:
                return error_response('Missing updates', 400)
            
            updates['updated_at'] = datetime.utcnow().isoformat()
            
            update_expr = "SET " + ", ".join([f"#{k}=:{k}" for k in updates.keys()])
            expr_names = {f"#{k}": k for k in updates.keys()}
            expr_values = {f":{k}": v for k, v in updates.items()}
            
            table.update_item(
                Key=key,
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values
            )
            
            print(f"[SUCCESS] Updated item: {item_id}")
            return success_response('แก้ไขข้อมูลสำเร็จ')
        
        else:
            return error_response(f'Invalid action: {action}', 400)
    
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(str(e), 500)

def success_response(message):
    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({'status': 'success', 'message': message}, ensure_ascii=False)
    }

def error_response(error, code=400):
    return {
        'statusCode': code,
        'headers': CORS_HEADERS,
        'body': json.dumps({'status': 'error', 'error': error}, ensure_ascii=False)
    }
