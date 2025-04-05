import os
from dotenv import load_dotenv
import plaid
from plaid.api import plaid_api
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from datetime import datetime, timedelta, date

class PlaidClient:
    def __init__(self):
        load_dotenv()
        
        configuration = plaid.Configuration(
            host=plaid.Environment.Sandbox if os.getenv('PLAID_ENV') == 'sandbox' else plaid.Environment.Development,
            api_key={
                'clientId': os.getenv('PLAID_CLIENT_ID'),
                'secret': os.getenv('PLAID_SECRET'),
            }
        )
        
        self.client = plaid_api.PlaidApi(plaid.ApiClient(configuration))
    
    def get_transactions(self, access_token, start_date=None, end_date=None):
        try:
            if not end_date:
                end_date = date.today()
            if not start_date:
                start_date = end_date - timedelta(days=30)
            
            options = TransactionsGetRequestOptions()
            request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=options
            )
            
            response = self.client.transactions_get(request)
            transactions = response.transactions
            
            while len(transactions) < response.total_transactions:
                options.offset = len(transactions)
                request = TransactionsGetRequest(
                    access_token=access_token,
                    start_date=start_date,
                    end_date=end_date,
                    options=options
                )
                response = self.client.transactions_get(request)
                transactions.extend(response.transactions)
            
            return transactions
            
        except plaid.ApiException as e:
            print(f"Error fetching transactions: {e}")
            return [] 