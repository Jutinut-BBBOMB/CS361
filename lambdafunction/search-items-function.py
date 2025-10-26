import json
import boto3
import os
import decimal

# --- (DecimalEncoder Class เหมือนเดิม) ---
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super(DecimalEncoder, self).default(obj)

# --- (ดึงชื่อ Table เหมือนเดิม) ---
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME'].strip()
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# --- (CORS Headers เหมือนเดิม) ---
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
}

def lambda_handler(event, context):
    
    # --- 1. (CORS Preflight เหมือนเดิม) ---
    if event['requestContext']['http']['method'] == 'OPTIONS':
        return {'statusCode': 204, 'headers': CORS_HEADERS, 'body': ''}
        
    # --- 2. (Parse JSON เหมือนเดิม) ---
    try:
        body = json.loads(event.get('body') or '{}')
        search_mode = body.get('search_mode', 'user') 
        keyword = body.get('keyword')
        location = body.get('location')
        date = body.get('date')
        status = body.get('status')
    except Exception as e:
        print(f"Error parsing input: {e}")
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': f'Invalid input data. {str(e)}'})}

    # --- 3. สร้าง FilterExpression แบบไดนามิก (ฉบับแก้ไข) ---
    filter_parts = []
    attr_values = {}
    attr_names = {}

    
    # --- ⭐️ (ใหม่!) ใช้ IF/ELSE เลือกเงื่อนไขตามผู้ใช้ ⭐️ ---
    
    if search_mode == 'admin':
        # --- 3A. Logic สำหรับ Admin (ค้นหาทุกอย่าง: 'FOUND_ITEM' และ 'LOST_REPORT') ---
        # ‼️ ไม่มีการ filter item_type ที่นี่ ‼️
        
        if date:
            # Admin ค้นหาได้ทั้ง 2 ช่อง (ของที่เจอ และ ของที่หาย)
            filter_parts.append("(foundDate = :date OR lostDate = :date)")
            attr_values[':date'] = date
        
        if status:
            filter_parts.append("#status_field = :status") 
            attr_names['#status_field'] = 'status'
            attr_values[':status'] = status
            
    else: 
        # --- 3B. Logic สำหรับ User (ค้นหาเฉพาะ 'FOUND_ITEM') ---
        
        # ‼️ Filter บังคับสำหรับ User (ย้ายมาไว้ตรงนี้) ‼️
        filter_parts.append("item_type = :item_type_filter")
        attr_values[':item_type_filter'] = 'FOUND_ITEM'
        
        # (เงื่อนไขของ User)
        if keyword:
            kw_part = "(contains(category, :keyword) OR contains(brandInfo, :keyword) OR contains(brandName, :keyword) OR contains(details, :keyword) OR contains(case_id, :keyword))"
            filter_parts.append(kw_part)
            attr_values[':keyword'] = keyword

        if location:
            filter_parts.append("contains(foundLocation, :location)")
            attr_values[':location'] = location

        if date:
            # User ค้นหาเฉพาะ foundDate
            filter_parts.append("foundDate = :date")
            attr_values[':date'] = date

        if status:
            filter_parts.append("#status_field = :status") 
            attr_names['#status_field'] = 'status'
            attr_values[':status'] = status
    
    # --- 4. (สร้างคำสั่ง Scan เหมือนเดิม) ---
    scan_params = {}
    if filter_parts:
        scan_params['FilterExpression'] = " AND ".join(filter_parts)
        scan_params['ExpressionAttributeValues'] = attr_values
        if attr_names:
            scan_params['ExpressionAttributeNames'] = attr_names
            
    try:
        response = table.scan(**scan_params)
        items = response.get('Items', [])
        count = response.get('Count', 0)
        
    except Exception as e:
        print(f"Error scanning DynamoDB: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': f'Failed to scan DynamoDB. {str(e)}'})}

    # --- 5. (ส่งคำตอบกลับ เหมือนเดิม) ---
    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'status': 'success',
            'count': count,
            'items': items
        }, cls=DecimalEncoder)
    }