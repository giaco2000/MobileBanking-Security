import hashlib
import re
import traceback
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import base64
import os
import firebase_admin
from firebase_admin import credentials, firestore
import json
import logger
import requests
from datetime import datetime
from flask_talisman import Talisman
import random
import string
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import pyotp
import uuid
import traceback


# Carica le variabili dal file .env
load_dotenv()

app = Flask(__name__)



# Carica le credenziali Firebase
firebase_credentials_path = "C:/Users/giaco/Desktop/Sicurezza Informatica/2_ANNO/Sicurezza delle Architetture orientate ai Servizi/progetto/mobilebanking-security-firebase-adminsdk-7inp2-45ee538f3a.json"
cred = credentials.Certificate(firebase_credentials_path)
firebase_admin.initialize_app(cred)

# Inizializza il database Firestore
db = firestore.client()

# Configurazione
app.secret_key = os.getenv("SECRET_KEY")
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)


# Configurazione rate limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)


# Configurazione Talisman per sicurezza Headers
talisman = Talisman(
    app,
    force_https=True,
    session_cookie_secure=True,
    frame_options='DENY',
    strict_transport_security=True,
    content_security_policy={
        'default-src': "'self'",
        'script-src': [
            "'self'", 
            "https://alcdn.msauth.net", 
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",  # Aggiunta questa riga per il qr code
            "'unsafe-inline'"
        ],
        'style-src': ["'self'", "https://fonts.googleapis.com", "'unsafe-inline'"],
        'font-src': ["'self'", "https://fonts.gstatic.com"],
        'img-src': ["'self'", 'data:', 'https:'],
        'connect-src': ["'self'", 'https://login.microsoftonline.com', 'https://github.com']
    }
)


# gestore di errori
@app.errorhandler(404)
def not_found_error(error):
    return "Pagina non trovata", 404

@app.errorhandler(500)
def internal_error(error):
    return "Errore interno del server", 500

@app.errorhandler(403)
def forbidden_error(error):
    return "Accesso negato", 403



# Funzioni helper per la crittografia
def encrypt_data(data, key):
    try:
        cipher = AES.new(bytes.fromhex(key), AES.MODE_EAX)
        nonce = cipher.nonce
        ciphertext, tag = cipher.encrypt_and_digest(data.encode('utf-8'))
        return base64.b64encode(nonce + ciphertext).decode('utf-8')
    except Exception as e:
        print(f"Errore durante la crittografia: {e}")
        raise

def decrypt_data(encrypted_data, key):
    try:
        raw_data = base64.b64decode(encrypted_data)
        nonce = raw_data[:16]
        ciphertext = raw_data[16:]
        cipher = AES.new(bytes.fromhex(key), AES.MODE_EAX, nonce=nonce)
        return cipher.decrypt(ciphertext).decode('utf-8')
    except Exception as e:
        print(f"Errore durante la decrittografia: {e}")
        raise


# Validazione IBAN lato server
def calculate_iban_check_digits(iban):
    """Calcola le cifre di controllo di un IBAN"""
    # Rimuove spazi e converte in maiuscolo
    iban = iban.replace(' ', '').upper()
    # Sposta i primi 4 caratteri alla fine
    iban = iban[4:] + iban[:4]
    # Converte lettere in numeri (A=10, B=11, ecc.)
    numerical = ''
    for char in iban:
        if char.isalpha():
            numerical += str(ord(char) - ord('A') + 10)
        else:
            numerical += char
    # Calcola il modulo
    return 98 - (int(numerical) % 97)

def validate_iban(iban):
    """Valida un IBAN"""
    try:
        # Log per debug
        print(f"Validazione IBAN originale: {iban}")
        
        # Rimuove spazi e converte in maiuscolo
        iban = iban.replace(' ', '').upper()
        print(f"IBAN formattato: {iban}")

        # Per IBAN italiani (che iniziano con IT)
        if iban.startswith('IT'):
            # Verifica lunghezza (27 caratteri per IBAN italiano)
            if len(iban) != 27:
                print(f"Lunghezza IBAN non valida. Attuale: {len(iban)}, Richiesta: 27")
                return False

            # Verifica pattern per IBAN italiano:
            # IT: codice paese (2 caratteri)
            # 12: cifre di controllo (2 numeri)
            # A: CIN (1 lettera)
            # 12345: ABI (5 numeri)
            # 12345: CAB (5 numeri)
            # 123456789012: Numero di conto (12 caratteri)
            iban_pattern = r'^IT\d{2}[A-Z]\d{5}\d{5}[A-Z0-9]{12}$'
            if not re.match(iban_pattern, iban):
                print("Pattern IBAN non valido")
                return False
            
            print("IBAN valido")
            return True
        else:
            # Per IBAN di altri paesi
            # Verifica base: almeno 2 lettere paese + 2 cifre di controllo
            if not re.match(r'^[A-Z]{2}\d{2}', iban):
                print("Formato base IBAN non valido")
                return False
            
            # Verifica lunghezza minima e massima generale
            if len(iban) < 15 or len(iban) > 27:
                print(f"Lunghezza IBAN non valida. Attuale: {len(iban)}")
                return False
            
            return True

    except Exception as e:
        print(f"Errore nella validazione IBAN: {str(e)}")
        return False

# Funzioni per gestire le transazioni
def create_transaction(encrypted_user_email, amount, recipient, description):
    """
    Aggiunge una nuova transazione al documento dell'utente e aggiorna il saldo
    """
    # Prepara i dati della transazione
    transaction_data = {
        'type': 'in' if amount >= 0 else 'out',
        'amount': float(abs(amount)),  # Assicuriamoci che sia un float
        'currency': 'EUR',
        'recipient': recipient,
        'description': description,
        'date': datetime.now().isoformat(),  # Convertiamo in stringa ISO
        'status': 'completed'
    }

    try:
        # Riferimento al documento utente
        user_ref = db.collection('users').document(encrypted_user_email)
        
        # Ottieni il documento corrente
        user_doc = user_ref.get()
        if not user_doc.exists:
            raise ValueError('Utente non trovato')

        user_data = user_doc.to_dict()
        current_balance = user_data.get('balance', 0)
        new_balance = current_balance + amount

        if new_balance < 0:
            raise ValueError('Saldo insufficiente')

        # Ottieni array transazioni esistente o crea nuovo
        transactions = user_data.get('transactions', [])
        transactions.append(transaction_data)

        # Aggiorna il documento
        user_ref.update({
            'balance': new_balance,
            'transactions': transactions
        })

        return new_balance, None

    except Exception as e:
        print(f"Errore dettagliato nella transazione: {str(e)}")
        raise



# Route per il login con Microsoft
@app.route('/login/microsoft')
@limiter.limit("5 per minute")
def microsoft_login():
    microsoft_auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    params = {
        "client_id": os.getenv("MICROSOFT_CLIENT_ID"),
        "response_type": "code",
        "redirect_uri": os.getenv("MICROSOFT_REDIRECT_URI"),
        "scope": "openid profile email user.read",
        "response_mode": "query"
    }
    auth_url = f"{microsoft_auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    return redirect(auth_url)



# callback di Microsoft
@app.route('/login/microsoft/callback')
def microsoft_callback():
    code = request.args.get('code')
    if not code:
        print("Parametri ricevuti:", request.args)  
        return "Errore: codice di autorizzazione mancante", 400

    try:
        # Ottieni il token
        token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        token_data = {
            "client_id": os.getenv("MICROSOFT_CLIENT_ID"),
            "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": os.getenv("MICROSOFT_REDIRECT_URI"),
            "grant_type": "authorization_code",
            "scope": "openid profile email user.read"
        }
        
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")

        # Ottieni info utente
        user_response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            }
        )
        user_response.raise_for_status()
        user_info = user_response.json()

        if 'mail' not in user_info:
            return "Errore: email non disponibile", 400

        key = os.getenv("AES_KEY")
        if not key:
            return "Errore: Chiave AES non configurata", 500

        email = user_info['mail']
        encrypted_email = encrypt_data(email, key)
        doc_id = hashlib.sha256(email.encode()).hexdigest()[:20]

        # Ottieni il documento utente esistente
        user_ref = db.collection('users').document(doc_id)
        user_doc = user_ref.get()
        
        # Prepara i dati dell'utente
        user_data = {
            "email": encrypted_email,
            "name": user_info.get('displayName', 'Anonymous'),
            "login_method": "Microsoft",
            "last_login": firestore.SERVER_TIMESTAMP,
        }

        if user_doc.exists:
            # Se l'utente esiste, mantieni il saldo esistente
            existing_data = user_doc.to_dict()
            user_data['balance'] = existing_data.get('balance', 0)
            if '2fa_secret' in existing_data:
                user_data['2fa_secret'] = existing_data['2fa_secret']
                user_data['2fa_enabled'] = existing_data.get('2fa_enabled', False)
        else:
            # Se è un nuovo utente, inizializza il saldo e la 2FA
            user_data['balance'] = 0
            secret = pyotp.random_base32()
            user_data['2fa_secret'] = encrypt_data(secret, key)
            user_data['2fa_enabled'] = False
            user_data['transactions'] = []

        # Aggiorna o crea il documento utente
        user_ref.set(user_data, merge=True)
        session['user'] = doc_id

        return redirect(url_for('dashboard'))

    except Exception as e:
        print(f"Errore durante l'autenticazione Microsoft:")
        print(traceback.format_exc())
        return "Si è verificato un errore durante l'autenticazione", 500


# Route per GitHub
@app.route('/login/github')
@limiter.limit("5 per minute")
def github_login():
    github_auth_url = "https://github.com/login/oauth/authorize"
    params = {
        "client_id": os.getenv("GITHUB_CLIENT_ID"),
        "redirect_uri": os.getenv("GITHUB_REDIRECT_URI"),
        "scope": "user:email"
    }
    auth_url = f"{github_auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    return redirect(auth_url)


# Callback di GitHub
@app.route('/login/github/callback')
def github_callback():
    code = request.args.get('code')
    if not code:
        return "Errore: codice di autorizzazione mancante", 400

    try:
        # Ottieni il token
        token_url = "https://github.com/login/oauth/access_token"
        token_data = {
            "client_id": os.getenv("GITHUB_CLIENT_ID"),
            "client_secret": os.getenv("GITHUB_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": os.getenv("GITHUB_REDIRECT_URI")
        }
        
        headers = {'Accept': 'application/json'}
        token_response = requests.post(token_url, data=token_data, headers=headers)
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")

        # Ottieni email utente
        user_response = requests.get(
            "https://api.github.com/user/emails",
            headers={
                'Authorization': f'token {access_token}',
                'Accept': 'application/json'
            }
        )
        user_response.raise_for_status()
        emails = user_response.json()
        primary_email = next(email["email"] for email in emails if email["primary"])

        # Ottieni info utente
        user_info_response = requests.get(
            "https://api.github.com/user",
            headers={
                'Authorization': f'token {access_token}',
                'Accept': 'application/json'
            }
        )
        user_info = user_info_response.json()

        key = os.getenv("AES_KEY")
        if not key:
            return "Errore: Chiave AES non configurata", 500

        encrypted_email = encrypt_data(primary_email, key)
        doc_id = hashlib.sha256(primary_email.encode()).hexdigest()[:20]

        # Ottieni il documento utente esistente
        user_ref = db.collection('users').document(doc_id)
        user_doc = user_ref.get()
        
        # Prepara i dati dell'utente
        user_data = {
            "email": encrypted_email,
            "name": user_info.get('name', 'Anonymous'),
            "login_method": "GitHub",
            "last_login": firestore.SERVER_TIMESTAMP,
        }

        if user_doc.exists:
            # Se l'utente esiste, mantieni il saldo esistente
            existing_data = user_doc.to_dict()
            user_data['balance'] = existing_data.get('balance', 0)
            if '2fa_secret' in existing_data:
                user_data['2fa_secret'] = existing_data['2fa_secret']
                user_data['2fa_enabled'] = existing_data.get('2fa_enabled', False)
        else:
            # Se è un nuovo utente, inizializza il saldo e la 2FA
            user_data['balance'] = 0
            secret = pyotp.random_base32()
            user_data['2fa_secret'] = encrypt_data(secret, key)
            user_data['2fa_enabled'] = False
            user_data['transactions'] = []

        # Aggiorna o crea il documento utente
        user_ref.set(user_data, merge=True)
        session['user'] = doc_id

        return redirect(url_for('dashboard'))

    except Exception as e:
        print(f"Errore durante l'autenticazione GitHub:")
        print(traceback.format_exc())
        return "Si è verificato un errore durante l'autenticazione", 500


# API: Recupero saldo
@app.route('/api/balance')
@limiter.limit("60 per minute")
def get_balance():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        encrypted_email = session['user']
        user_doc = db.collection('users').document(encrypted_email).get()

        if not user_doc.exists:
            return jsonify({"error": "Utente non trovato"}), 404

        user_data = user_doc.to_dict()
        # Se balance non esiste, ritorna 0
        balance = user_data.get('balance', 0)
        
        return jsonify({"balance": balance})

    except Exception as e:
        print(f"Errore nel recupero del saldo: {e}")
        return jsonify({"error": "Errore interno"}), 500


# API: Recupero delle transazioni
@app.route('/api/transactions')
@limiter.limit("60 per minute")
def get_transactions():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        # Ottieni il documento utente
        user_ref = db.collection('users').document(session['user'])
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"error": "Utente non trovato"}), 404

        user_data = user_doc.to_dict()
        transactions = user_data.get('transactions', [])

        # Ottieni la chiave AES
        key = os.getenv("AES_KEY")
        if not key:
            return jsonify({"error": "Errore di configurazione"}), 500

        # Decifra i dati sensibili per ogni transazione
        decrypted_transactions = []
        for trans in sorted(transactions, key=lambda x: x['date'], reverse=True)[:10]:
            decrypted_trans = {
                'type': trans['type'],
                'amount': trans['amount'],
                'recipient': decrypt_data(trans['recipient'], key),
                'iban': decrypt_data(trans['iban'], key),
                'description': decrypt_data(trans['description'], key),
                'date': trans['date'],
                'status': trans['status'],
                'transaction_id': trans['transaction_id']
            }
            decrypted_transactions.append(decrypted_trans)

        return jsonify({"transactions": decrypted_transactions})

    except Exception as e:
        print(f"Errore nel recupero delle transazioni: {e}")
        print(traceback.format_exc())
        return jsonify({"error": "Errore interno"}), 500


# transazioni verificate
@app.route('/api/transactions/verify', methods=['POST'])
@limiter.limit("10 per minute")
def verify_transaction():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        data = request.json
        print("Dati transazione ricevuti:", data)  # Debug log

        if not data or 'otp' not in data or 'iban' not in data:
            return jsonify({"error": "Dati mancanti"}), 400
        
        if 'iban' not in data:
            return jsonify({"error": "Dati mancanti - IBAN richiesto"}), 400

        # Validazione IBAN
        if not validate_iban(data['iban']):
            return jsonify({"error": "IBAN non valido. Formato richiesto: IT00X0000000000000000000000"}), 400


        # Ottieni il documento utente
        user_ref = db.collection('users').document(session['user'])
        user_doc = user_ref.get()

        
        if not user_doc.exists:
            return jsonify({"error": "Utente non trovato"}), 404

        user_data = user_doc.to_dict()

        # Verifica 2FA
        key = os.getenv("AES_KEY")
        if not key:
            return jsonify({"error": "Errore di configurazione"}), 500

        secret = decrypt_data(user_data['2fa_secret'], key)
        totp = pyotp.TOTP(secret)

        # Aggiungiamo più debug logs
        print(f"Codice ricevuto: {data['otp']}")
        print(f"Secret decifrato: {secret}")
        
        if not totp.verify(data['otp'], valid_window=1):
            print("Verifica 2FA fallita")
            return jsonify({"error": "Codice 2FA non valido"}), 400

        # Verifica il saldo
        current_balance = user_data.get('balance', 0)
        transaction_amount = float(data['amount'])

        if current_balance < transaction_amount:
            return jsonify({"error": "Saldo insufficiente"}), 400

        # Prepara i dati cifrati della transazione
        transaction_data = {
            'type': 'out',
            'amount': transaction_amount,
            'recipient': encrypt_data(data['recipient'], key),
            'iban': encrypt_data(data['iban'], key),
            'description': encrypt_data(data.get('description', ''), key),
            'date': datetime.now().isoformat(),
            'status': 'completed',
            'transaction_id': str(uuid.uuid4())
        }

        # Calcola il nuovo saldo
        new_balance = current_balance - transaction_amount

        # Aggiorna il documento dell'utente
        transactions = user_data.get('transactions', [])
        transactions.append(transaction_data)
        
        user_ref.update({
            'balance': new_balance,
            'transactions': transactions
        })

        # Prepara le transazioni decifrate per il client
        decrypted_transactions = []
        for trans in sorted(transactions, key=lambda x: x['date'], reverse=True)[:10]:
            decrypted_trans = {
                'type': trans['type'],
                'amount': trans['amount'],
                'recipient': decrypt_data(trans['recipient'], key),
                'iban': decrypt_data(trans['iban'], key),
                'description': decrypt_data(trans['description'], key),
                'date': trans['date'],
                'status': trans['status'],
                'transaction_id': trans['transaction_id']
            }
            decrypted_transactions.append(decrypted_trans)

        return jsonify({
            "message": "Transazione completata con successo",
            "new_balance": new_balance,
            "transactions": decrypted_transactions
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Errore nella verifica della transazione: {e}")
        print(traceback.format_exc())
        return jsonify({"error": "Errore interno"}), 500


# API: Creazione di una nuova transazione
@app.route('/api/transactions', methods=['POST'])
@limiter.limit("10 per minute")
def create_new_transaction():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        data = request.json
        if not data or 'amount' not in data or 'recipient' not in data:
            return jsonify({"error": "Dati non validi"}), 400

        encrypted_email = session['user']  # Usiamo l'email cifrata dalla sessione
        amount = float(data['amount'])
        
        # Validazione dell'importo
        if amount >= 0 and data.get('type') == 'out':
            amount = -amount  # Rendiamo negativo l'importo per i prelievi

        new_balance, transaction_id = create_transaction(
            encrypted_email,
            amount,
            data['recipient'],
            data.get('description', '')
        )

        return jsonify({
            "message": "Transazione creata con successo",
            "transaction_id": transaction_id,
            "new_balance": new_balance
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Errore nella creazione della transazione: {e}")
        return jsonify({"error": "Errore interno"}), 500



# Endpoint per richiedere l'OTP
@app.route('/api/deposit/request-otp', methods=['POST'])
@limiter.limit("3 per minute")
def request_deposit_otp():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        data = request.json
        amount = float(data.get('amount', 0))

        # Validazione dell'importo
        if amount <= 0 or amount > 10000:
            return jsonify({"error": "Importo non valido"}), 400

        # Recupera il documento dell'utente
        user_ref = db.collection('users').document(session['user'])
        user_doc = user_ref.get()
        user_data = user_doc.to_dict()
        
        if not user_doc.exists:
            return jsonify({"error": "Utente non trovato"}), 404

        # Decifra il secret 2FA e genera l'URI
        secret = decrypt_data(user_data['2fa_secret'], os.getenv("AES_KEY"))
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=decrypt_data(user_data['email'], os.getenv("AES_KEY")),
            issuer_name="MobileBanking Security"
        )

        # Salva l'importo da depositare temporaneamente
        user_ref.update({
            'pending_deposit': {
                'amount': amount,
                'expires': datetime.now() + timedelta(minutes=5)
            }
        })

        return jsonify({
            "message": "OTP richiesto",
            "qr_uri": provisioning_uri
        })

    except Exception as e:
        print(f"Errore nella richiesta deposito: {e}")
        return jsonify({"error": "Errore interno"}), 500


# Endpoint per verificare l'OTP e completare il deposito
@app.route('/api/deposit/verify-otp', methods=['POST'])
@limiter.limit("20 per minute")
def verify_deposit_otp():
    try:
        data = request.json
        submitted_code = data.get('otp')
        amount = data.get('amount')
        
        print(f"Codice ricevuto: {submitted_code}")
        print(f"Importo ricevuto: {amount}")

        # Recupera il documento dell'utente
        user_ref = db.collection('users').document(session['user'])
        user_doc = user_ref.get()
        user_data = user_doc.to_dict()

        # Decifra e verifica il codice
        secret = decrypt_data(user_data['2fa_secret'], os.getenv("AES_KEY"))
        totp = pyotp.TOTP(secret)
        
        # Aggiungi una finestra di tempo più ampia (30 secondi prima e dopo)
        is_valid = totp.verify(submitted_code, valid_window=1)
        print(f"Verifica codice: {is_valid}")

        if not is_valid:
            return jsonify({"error": "Codice non valido"}), 400

        # Calcola il nuovo saldo
        current_balance = user_data.get('balance', 0)
        new_balance = current_balance + amount

        # Aggiorna il saldo
        user_ref.update({
            'balance': new_balance,
            '2fa_enabled': True
        })

        print(f"Saldo aggiornato: {new_balance}")

        return jsonify({
            "message": "Deposito completato con successo",
            "new_balance": new_balance
        })

    except Exception as e:
        print(f"Errore nella verifica OTP: {e}")
        return jsonify({"error": "Errore interno"}), 500


# route per il qr code iniziale
@app.route('/api/2fa/setup')
def get_2fa_setup():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        user_doc = db.collection('users').document(session['user']).get()
        user_data = user_doc.to_dict()
        
        print("User data:", user_data)  # Debug log
        
        # Genera un nuovo secret se non esiste
        if '2fa_secret' not in user_data:
            secret = pyotp.random_base32()
            encrypted_secret = encrypt_data(secret, os.getenv("AES_KEY"))
            user_doc.reference.update({
                '2fa_secret': encrypted_secret,
                '2fa_enabled': False
            })
        else:
            secret = decrypt_data(user_data['2fa_secret'], os.getenv("AES_KEY"))

        print("Secret:", secret)  # Debug log
        
        # Genera l'URI per il QR code
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=decrypt_data(user_data['email'], os.getenv("AES_KEY")),
            issuer_name="MobileBanking Security"
        )
        
        print("URI generato:", provisioning_uri)  # Debug log

        return jsonify({
            "qr_uri": provisioning_uri
        })

    except Exception as e:
        print(f"Errore dettagliato nel setup 2FA: {e}")
        print(traceback.format_exc())  # Stampa il traceback completo
        return jsonify({"error": "Errore interno"}), 500


# ROUTE per conferma 2fa
@app.route('/api/2fa/confirm-setup', methods=['POST'])
def confirm_2fa_setup():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        user_ref = db.collection('users').document(session['user'])
        user_ref.update({
            '2fa_enabled': True
        })
        return jsonify({"message": "Setup 2FA completato"}), 200
    except Exception as e:
        print(f"Errore nella conferma setup 2FA: {e}")
        return jsonify({"error": "Errore interno"}), 500


# route per il check-status 2fa
@app.route('/api/2fa/check-status')
def check_2fa_status():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        user_doc = db.collection('users').document(session['user']).get()
        user_data = user_doc.to_dict()
        
        # Controlla se l'utente ha già configurato il 2FA
        is_configured = user_data.get('2fa_enabled', False)
        
        return jsonify({
            "is_configured": is_configured
        })
    except Exception as e:
        print(f"Errore nel controllo stato 2FA: {e}")
        return jsonify({"error": "Errore interno"}), 500



# route per i tassi di cambio con l'API
@app.route('/api/exchange-rates')
@limiter.limit("30 per minute")
def get_exchange_rates():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        api_key = os.getenv('EXCHANGE_RATE_API_KEY')
        base_currency = 'EUR'  # La nostra valuta base
        
        # Chiamata all'API
        response = requests.get(f'https://v6.exchangerate-api.com/v6/{api_key}/latest/{base_currency}')
        response.raise_for_status()
        
        rates = response.json()
        return jsonify({
            "base": rates['base_code'],
            "rates": {
                "USD": rates['conversion_rates']['USD'],
                "GBP": rates['conversion_rates']['GBP'],
                "JPY": rates['conversion_rates']['JPY'],
                "CHF": rates['conversion_rates']['CHF'],
                "AUD": rates['conversion_rates']['AUD']
            }
        })

    except Exception as e:
        print(f"Errore nel recupero dei tassi di cambio: {e}")
        return jsonify({"error": "Errore nel recupero dei tassi di cambio"}), 500


@app.route('/api/convert', methods=['POST'])
@limiter.limit("30 per minute")
def convert_currency():
    if 'user' not in session:
        return jsonify({"error": "Non autorizzato"}), 401

    try:
        data = request.json
        if not data or 'amount' not in data or 'to_currency' not in data:
            return jsonify({"error": "Dati mancanti"}), 400

        amount = float(data['amount'])
        to_currency = data['to_currency']
        
        # Ottieni il tasso di cambio
        api_key = os.getenv('EXCHANGE_RATE_API_KEY')
        response = requests.get(f'https://v6.exchangerate-api.com/v6/{api_key}/pair/EUR/{to_currency}')
        response.raise_for_status()
        
        rate = response.json()['conversion_rate']
        converted_amount = amount * rate

        return jsonify({
            "from": "EUR",
            "to": to_currency,
            "amount": amount,
            "rate": rate,
            "result": round(converted_amount, 2)
        })

    except Exception as e:
        print(f"Errore nella conversione: {e}")
        return jsonify({"error": "Errore nella conversione"}), 500



# Route per la dashboard
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        session.clear()
        return redirect(url_for('home'))

    try:
        encrypted_email = session['user']
        user_doc = db.collection('users').document(encrypted_email).get()
        
        if not user_doc.exists:
            return "Utente non trovato!", 404

        user = user_doc.to_dict()

        # Recupera l'ultima transazione
        last_transaction = None
        transactions = (
            db.collection('transactions')
            .where('user_email', '==', encrypted_email)
            .order_by('date', direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )

        for transaction in transactions:
            last_transaction = transaction.to_dict()
            break

        if not last_transaction:
            last_transaction = {"amount": 0, "date": datetime.now()}

        # Calcola spese mensili
        current_month = datetime.now().replace(day=1)
        monthly_expenses = 0
        monthly_transactions = (
            db.collection('transactions')
            .where('user_email', '==', encrypted_email)
            .where('type', '==', 'out')
            .where('date', '>=', current_month)
            .stream()
        )

        for transaction in monthly_transactions:
            monthly_expenses += transaction.to_dict().get('amount', 0)

        return render_template(
            'dashboard.html',
            user=user,
            balance=user.get('balance', 0),
            last_transaction=last_transaction,
            monthly_expenses=monthly_expenses
        )

    except Exception as e:
        print(f"Errore nel caricamento della dashboard: {e}")
        import traceback
        print(traceback.format_exc())
        return "Si è verificato un errore", 500


# Route per il logout
@app.route('/logout')
def logout():
    # Pulisci la sessione
    session.clear()
    # Invalida eventuali cookie
    response = redirect(url_for('home'))
    response.delete_cookie('session')
    return response


# route principale
@app.route('/')
def home():
    session.clear()
    return render_template('index.html',
                         microsoft_client_id=os.getenv('MICROSOFT_CLIENT_ID'),
                         github_client_id=os.getenv('GITHUB_CLIENT_ID'))


# Avvia l'app
if __name__ == '__main__':
    app.run(debug=True)

