import json
import boto3
import os
import decimal
from boto3.dynamodb.conditions import Key, Attr


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)


DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'Items_TU')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)


CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS, GET',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
}


def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    
    # CORS Preflight
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {
            'statusCode': 200,  # ⚠️ เปลี่ยนจาก 204 เป็น 200
            'headers': CORS_HEADERS,
            'body': json.dumps({'status': 'ok'})
        }
    
    try:
        body = json.loads(event.get('body', '{}'))
        print(f"Search params: {body}")
        
        # ⚠️ รับตัวแปรทั้งหมด (เพิ่ม status และ search_mode)
        search_mode = body.get('search_mode', '')  # ✅ เพิ่มใหม่
        keyword = body.get('keyword', '').strip()
        location = body.get('location', '').strip()
        date = body.get('date', '').strip()
        more_details = body.get('moreDetails', '').strip()
        status_filter = body.get('status', '').strip()  # ✅ เพิ่มใหม่
        
        print(f"search_mode: {search_mode}, status: {status_filter}")
        
        # ✅ ถ้าเป็น admin mode และมี status filter ให้ใช้ GSI
        if search_mode == 'admin' and status_filter:
            print(f"[ADMIN MODE] Querying by status: {status_filter}")
            try:
                response = table.query(
                    IndexName='GSI1',
                    KeyConditionExpression=Key('gsi1_pk').eq(f'STATUS#{status_filter}')
                )
                all_items = response.get('Items', [])
                print(f"[GSI Query] Found {len(all_items)} items with status {status_filter}")
            except Exception as gsi_error:
                print(f"[WARN] GSI query failed: {gsi_error}")
                print("[INFO] Falling back to Scan with filter")
                # ถ้า GSI ไม่มี ใช้ Scan + FilterExpression แทน
                response = table.scan(
                    FilterExpression=Attr('status').eq(status_filter)
                )
                all_items = response.get('Items', [])
        else:
            # Scan ทั้งตาราง (กรณีไม่มี status filter)
            print("[INFO] Scanning all items")
            response = table.scan()
            all_items = response.get('Items', [])
        
        # ✅ กรองทั้ง FOUND และ LOST
        filtered_items = [
            item for item in all_items 
            if item.get('item_type') in ['FOUND', 'LOST']
        ]
        
        print(f"Total items before filtering: {len(filtered_items)}")
        print(f"  FOUND: {len([i for i in filtered_items if i.get('item_type') == 'FOUND'])}")
        print(f"  LOST: {len([i for i in filtered_items if i.get('item_type') == 'LOST'])}")
        
        # ฟังก์ชันค้นหาแบบยืดหยุ่น
        def normalize_text(text):
            if not text:
                return ''
            return str(text).lower().replace(' ', '').replace('.', '').replace('-', '')
        
        def contains_flexible(field_value, search_term):
            if not search_term:
                return True
            if not field_value:
                return False
            normalized_field = normalize_text(field_value)
            normalized_search = normalize_text(search_term)
            return normalized_search in normalized_field
        
        # กรองตาม keyword
        if keyword:
            filtered_items = [
                item for item in filtered_items
                if (
                    contains_flexible(item.get('category', ''), keyword) or
                    contains_flexible(item.get('brand', ''), keyword) or
                    contains_flexible(item.get('details', ''), keyword) or
                    contains_flexible(item.get('case_id', ''), keyword)
                )
            ]
            print(f"After keyword filter: {len(filtered_items)} items")
        
        # กรองตาม location
        if location:
            filtered_items = [
                item for item in filtered_items
                if contains_flexible(item.get('location', ''), location)
            ]
            print(f"After location filter: {len(filtered_items)} items")
        
        # กรองตาม date
        if date:
            filtered_items = [
                item for item in filtered_items
                if item.get('date') == date
            ]
            print(f"After date filter: {len(filtered_items)} items")
        
        # กรองตาม more_details
        if more_details:
            filtered_items = [
                item for item in filtered_items
                if contains_flexible(item.get('details', ''), more_details)
            ]
            print(f"After more_details filter: {len(filtered_items)} items")
        
        # เรียงตามวันที่ล่าสุด
        filtered_items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        print(f"Final result: {len(filtered_items)} items")
        
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'success',
                'count': len(filtered_items),
                'items': filtered_items
            }, cls=DecimalEncoder, ensure_ascii=False)
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'status': 'error',
                'error': str(e)
            }, ensure_ascii=False)
        }
