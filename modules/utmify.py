import requests
import json
from datetime import datetime
import pytz

print("✅ Módulo utmify carregado!")

class UtmifyAPI:
    def __init__(self):
        self.api_url = "https://api.utmify.com.br/api-credentials/orders"
        self.brasilia_tz = pytz.timezone('America/Sao_Paulo')
    
    def format_datetime_utc(self, dt=None):
        """Formata datetime para UTC no formato esperado pela Utmify"""
        if dt is None:
            dt = datetime.now(self.brasilia_tz)
        
        # Converte para UTC
        utc_dt = dt.astimezone(pytz.UTC)
        return utc_dt.strftime('%Y-%m-%d %H:%M:%S')
    
    async def send_pix_generated(self, api_token, order_data, tracking_data):
        """Envia evento de PIX gerado para Utmify"""
        
        headers = {
            'x-api-token': api_token,
            'Content-Type': 'application/json'
        }
        
        # Monta o payload
        payload = {
            "orderId": order_data['transaction_id'],
            "platform": "TelegramBot",
            "paymentMethod": "pix",
            "status": "waiting_payment",
            "createdAt": self.format_datetime_utc(),
            "approvedDate": None,
            "refundedAt": None,
            "customer": {
                "name": f"User {order_data['user_id']}",
                "email": f"u{order_data['user_id']}@telegram.local",
                "phone": None,
                "document": None,
                "country": "BR",
                "ip": "127.0.0.1"
            },
            "products": [
                {
                    "id": f"{order_data['transaction_id']}",
                    "name": f"{order_data['plan_name']} - Bot {order_data['bot_id']}",
                    "planId": None,
                    "planName": None,
                    "quantity": 1,
                    "priceInCents": int(order_data['value'] * 100)
                }
            ],
            "trackingParameters": {
                "src": tracking_data.get('src'),
                "sck": tracking_data.get('sck'),
                "utm_source": tracking_data.get('utm_source'),
                "utm_campaign": tracking_data.get('utm_campaign'),
                "utm_medium": tracking_data.get('utm_medium'),
                "utm_content": tracking_data.get('utm_content'),
                "utm_term": tracking_data.get('utm_term')
            },
            "commission": {
                "totalPriceInCents": int(order_data['value'] * 100),
                "gatewayFeeInCents": 0,  # SIMPLIFICADO - cliente configura na Utmify
                "userCommissionInCents": int(order_data['value'] * 100),  # Valor total
                "currency": "BRL"
            },
            "isTest": False
        }
        
        try:
            response = requests.post(self.api_url, json=payload, headers=headers)
            
            if response.status_code in [200, 201]:
                print(f"[UTMIFY] PIX gerado enviado com sucesso!")
                print(f"  Order: {order_data['transaction_id']}")
                print(f"  Valor: R$ {order_data['value']}")
                print(f"  Campaign: {tracking_data.get('utm_campaign', 'N/A')}")
                return True
            else:
                print(f"[UTMIFY] Erro ao enviar PIX gerado: {response.status_code}")
                print(f"  Resposta: {response.text}")
                return False
                
        except Exception as e:
            print(f"[UTMIFY] Erro na requisição: {e}")
            return False
    
    async def send_purchase_completed(self, api_token, order_data, tracking_data):
        """Envia evento de compra aprovada para Utmify"""
        
        headers = {
            'x-api-token': api_token,
            'Content-Type': 'application/json'
        }
        
        # Data de criação e aprovação
        created_at = order_data.get('created_at', self.format_datetime_utc())
        approved_at = self.format_datetime_utc()
        
        # Monta o payload
        payload = {
            "orderId": order_data['transaction_id'],
            "platform": "TelegramBot",
            "paymentMethod": "pix",
            "status": "paid",
            "createdAt": created_at,
            "approvedDate": approved_at,
            "refundedAt": None,
            "customer": {
                "name": f"User {order_data['user_id']}",
                "email": f"u{order_data['user_id']}@telegram.local",
                "phone": None,
                "document": None,
                "country": "BR",
                "ip": "127.0.0.1"
            },
            "products": [
                {
                    "id": f"{order_data['transaction_id']}",
                    "name": f"{order_data['plan_name']} - Bot {order_data['bot_id']}",
                    "planId": None,
                    "planName": None,
                    "quantity": 1,
                    "priceInCents": int(order_data['value'] * 100)
                }
            ],
            "trackingParameters": {
                "src": tracking_data.get('src'),
                "sck": tracking_data.get('sck'),
                "utm_source": tracking_data.get('utm_source'),
                "utm_campaign": tracking_data.get('utm_campaign'),
                "utm_medium": tracking_data.get('utm_medium'),
                "utm_content": tracking_data.get('utm_content'),
                "utm_term": tracking_data.get('utm_term')
            },
            "commission": {
                "totalPriceInCents": int(order_data['value'] * 100),
                "gatewayFeeInCents": 0,  # SIMPLIFICADO - cliente configura na Utmify
                "userCommissionInCents": int(order_data['value'] * 100),  # Valor total
                "currency": "BRL"
            },
            "isTest": False
        }
        
        try:
            response = requests.post(self.api_url, json=payload, headers=headers)
            
            if response.status_code in [200, 201]:
                print(f"[UTMIFY] Compra enviada com sucesso!")
                print(f"  Order: {order_data['transaction_id']}")
                print(f"  Valor: R$ {order_data['value']}")
                print(f"  Campaign: {tracking_data.get('utm_campaign', 'N/A')}")
                return True
            else:
                print(f"[UTMIFY] Erro ao enviar compra: {response.status_code}")
                print(f"  Resposta: {response.text}")
                return False
                
        except Exception as e:
            print(f"[UTMIFY] Erro na requisição: {e}")
            return False

# Instância global

utmify_api = UtmifyAPI()


