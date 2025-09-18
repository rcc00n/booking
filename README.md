### Commands:


Kill the port:
```
fuser -k 8000/tcp
```

Command to activate the enviroment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Command to start the server:
```bash
python manage.py runserver
```

Command to make migration:
```bash
python manage.py makemigrations
```

Command to migrate:
```bash
python manage.py migrate
```

Command to add superuser to the Admin panel:
```bash
python manage.py createsuperuser
```

Pages:

http://127.0.0.1:8000/admin/ - admin panel login

http://127.0.0.1:8000/accounts/login/ - general login


Test accounts:

  Admin:
  
    UN: Vadim
    
    P: 7238523qwQW!
    
  User:
  
    UN: user
    
P: useruser!!!

### Stripe payments

Add these variables to your `.env` (or environment) before running the server:

```
STRIPE_PUBLIC_KEY=pk_live_or_test
STRIPE_SECRET_KEY=sk_live_or_test
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CURRENCY=cad
STRIPE_PAYMENT_METHOD_TYPES=card
```

Run migrations to apply the new payment fields:

```
python manage.py migrate
```

Expose the webhook endpoint when running locally, e.g. with Stripe CLI:

```
stripe listen --forward-to localhost:8000/stripe/webhook/
```

Client checkout now requires Stripe.js. The cart checkout API returns a PaymentIntent client secret; the portal will open a secure modal where the customer can finish payment.
