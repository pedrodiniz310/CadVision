# Crie um arquivo test_cosmos.py na pasta backend
from app.services.cosmos_service import fetch_product_by_gtin

result = fetch_product_by_gtin("7891340365576")
print(result)