// Gestione della navigazione
document.addEventListener('DOMContentLoaded', function() {
    // Seleziona tutti i menu item e le sezioni
    const menuItems = document.querySelectorAll('.menu-item');
    const sections = document.querySelectorAll('.content-section');

    
    // Gestione del click sui menu item
    menuItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Rimuove la classe active da tutti i menu item e sezioni
            menuItems.forEach(i => i.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));
            
            // Aggiunge la classe active al menu item cliccato
            item.classList.add('active');
            
            // Mostra la sezione corrispondente
            const sectionId = item.getAttribute('data-section');
            document.getElementById(sectionId).classList.add('active');
        });
    });

    // Carica i dati iniziali
    loadDashboardData();
});



// Funzione per caricare i dati della dashboard
async function loadDashboardData() {
    try {
        // Carica il saldo
        const balanceResponse = await fetch('/api/balance');
        const balanceData = await balanceResponse.json();
        updateBalance(balanceData.balance);

        // Carica le transazioni
        const transactionsResponse = await fetch('/api/transactions');
        const transactionsData = await transactionsResponse.json();
        updateTransactionsList(transactionsData.transactions);

        // Inizializza la sezione tassi di cambio
        initializeDashboard();
    } catch (error) {
        console.error('Errore nel caricamento dei dati:', error);
        showError('Si è verificato un errore nel caricamento dei dati');
    }
}

// Aggiunte queste nuove funzioni per la validazione IBAN
function validateIBAN(iban) {
    const ibanPattern = /^[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}([A-Z0-9]?){0,16}$/;
    return ibanPattern.test(iban.replace(/\s/g, ''));
}

function formatIBAN(iban) {
    return iban.replace(/\s/g, '').replace(/(.{4})/g, '$1 ').trim();
}

// Funzione per mostrare il modale di deposito
async function showDepositModal() {
    try {
        // Prima mostra il modale per inserire l'importo
        document.getElementById('depositModal').style.display = "block";
    } catch (error) {
        console.error('Errore:', error);
        showError('Errore nel caricamento del modale');
    }
}


// Funzione per chiudere tutti i modali
function closeModals() {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => modal.style.display = "none");
}

// Chiudi i modali se si clicca fuori
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        closeModals();
    }
}


// Aggiorniamo anche il gestore del deposito per usare 2FA
// Gestione del form di deposito
document.getElementById('depositForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const amount = document.getElementById('depositAmount').value;
    
    try {
        const setupResponse = await fetch('/api/2fa/setup');
        const setupData = await setupResponse.json();
        
        if (setupData.qr_uri) {
            const qrCodeContainer = document.getElementById('qrCodeContainer');
            qrCodeContainer.innerHTML = '';
            
            // Crea un elemento canvas
            const canvas = document.createElement('canvas');
            qrCodeContainer.appendChild(canvas);
            
            // Genera il QR code usando QRious
            new QRious({
                element: canvas,
                value: setupData.qr_uri,
                size: 256
            });
            
            document.getElementById('depositModal').style.display = "none";
            document.getElementById('setupTwoFactorModal').style.display = "block";
            sessionStorage.setItem('pendingAmount', amount);
        }
    } catch (error) {
        console.error('Errore:', error);
        showError('Errore nella richiesta');
    }
});


// Gestore della verifica 2FA
document.getElementById('twoFactorForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const code = document.getElementById('otpCode').value;
    const amount = sessionStorage.getItem('pendingAmount');
    
    console.log("Amount from sessionStorage:", amount);
    console.log("Code entered:", code);

    if (!amount) {
        showError('Nessun importo specificato per il deposito');
        return;
    }

    try {
        const response = await fetch('/api/deposit/verify-otp', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                otp: code,
                amount: parseFloat(amount)
            })
        });

        const data = await response.json();
        
        if (response.ok) {
            // Aggiorna il saldo e chiudi i modali
            updateBalance(data.new_balance);
            closeModals();
            sessionStorage.removeItem('pendingAmount');
            showSuccess('Deposito completato con successo');
            
            // Reset dei form
            document.getElementById('depositForm').reset();
            document.getElementById('twoFactorForm').reset();
        } else {
            showError(data.error || 'Codice non valido');
        }
    } catch (error) {
        console.error('Errore:', error);
        showError('Errore di connessione');
    }
});


// Funzione per aggiornare il saldo visualizzato
function updateBalance(newBalance) {
    const balanceElement = document.querySelector('.balance-amount');
    if (balanceElement) {
        balanceElement.textContent = `€ ${newBalance.toFixed(2)}`;
    }
}

// Aggiorna la lista delle transazioni
function updateTransactionsList(transactions) {
    const transactionsList = document.querySelector('.transactions-list');
    if (!transactionsList) return;

    transactionsList.innerHTML = '';
    
    if (!transactions || transactions.length === 0) {
        transactionsList.innerHTML = `
            <div class="no-transactions">
                <p>Nessuna transazione effettuata</p>
            </div>
        `;
        return;
    }
    
    transactions.forEach(transaction => {
        const transactionItem = document.createElement('div');
        transactionItem.className = 'transaction-item';
        
        const amountClass = transaction.type === 'out' ? 'text-danger' : 'text-success';
        const amountPrefix = transaction.type === 'out' ? '-' : '+';
        const formattedDate = new Date(transaction.date).toLocaleString('it-IT');

        transactionItem.innerHTML = `
            <div class="transaction-info">
                <div class="transaction-header">
                    <span class="transaction-name">${transaction.recipient}</span>
                    <span class="transaction-amount ${amountClass}">
                        ${amountPrefix} € ${transaction.amount.toFixed(2)}
                    </span>
                </div>
                <div class="transaction-details">
                    <div class="transaction-iban">IBAN: ${formatIBAN(transaction.iban)}</div>
                    <div class="transaction-description">${transaction.description}</div>
                    <div class="transaction-date">${formattedDate}</div>
                </div>
            </div>
        `;
        
        transactionsList.appendChild(transactionItem);
    });
}


// Gestione del form delle transazioni
const transactionForm = document.getElementById('transaction-form');
if (transactionForm) {
    transactionForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(transactionForm);
        const iban = formData.get('iban').replace(/\s/g, '');
        const amount = parseFloat(formData.get('amount'));

        if (!validateIBAN(iban)) {
            showError('IBAN non valido');
            return;
        }

        const transactionData = {
            recipient: formData.get('beneficiary'),
            iban: iban,
            amount: amount,
            description: formData.get('description')
        };

        try {
            // Verifica saldo
            const balanceResponse = await fetch('/api/balance');
            const balanceData = await balanceResponse.json();
            
            if (balanceData.balance < amount) {
                showError('Saldo insufficiente per effettuare questa transazione');
                return;
            }

            // Verifica stato 2FA
            const twoFAResponse = await fetch('/api/2fa/check-status');
            const twoFAData = await twoFAResponse.json();

            if (!twoFAData.is_configured) {
                // Se 2FA non è configurato, usa il setup esistente
                const setupResponse = await fetch('/api/2fa/setup');
                const setupData = await setupResponse.json();
                
                if (setupData.qr_uri) {
                    const qrCodeContainer = document.getElementById('qrCodeContainer');
                    qrCodeContainer.innerHTML = '';
                    
                    const canvas = document.createElement('canvas');
                    qrCodeContainer.appendChild(canvas);
                    
                    new QRious({
                        element: canvas,
                        value: setupData.qr_uri,
                        size: 256
                    });
                    
                    document.getElementById('setupTwoFactorModal').style.display = "block";
                    sessionStorage.setItem('pendingTransaction', JSON.stringify(transactionData));
                }
            } else {
                // Se 2FA è già configurato, mostra direttamente il modale OTP
                document.getElementById('transactionOtpModal').style.display = 'block';
                sessionStorage.setItem('pendingTransaction', JSON.stringify(transactionData));
            }
        } catch (error) {
            console.error('Errore:', error);
            showError('Si è verificato un errore durante la verifica');
        }
    });
}

// Aggiunto il gestore per la verifica OTP delle transazioni
document.getElementById('transactionOtpForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const code = document.getElementById('transactionOtpCode').value;
    const transactionData = JSON.parse(sessionStorage.getItem('pendingTransaction'));
    
    try {
        console.log('Dati transazione:', transactionData); // Per debug
        
        const response = await fetch('/api/transactions/verify', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                otp: code,
                ...transactionData
            })
        });

        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Errore durante la transazione');
        }

        // Se la transazione va a buon fine
        updateBalance(data.new_balance);
        updateTransactionsList(data.transactions);
        
        // Chiudi il modale e pulisci i form
        document.getElementById('transactionOtpModal').style.display = 'none';
        document.getElementById('transaction-form').reset();
        document.getElementById('transactionOtpForm').reset();
        sessionStorage.removeItem('pendingTransaction');
        
        showSuccess('Transazione completata con successo');
    } catch (error) {
        console.error('Errore:', error);
        showError(error.message || 'Errore durante la transazione');
    }
});


// Tassi di cambio
async function loadExchangeRates() {
    try {
        const response = await fetch('/api/exchange-rates');
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }

        const exchangeRatesElement = document.getElementById('exchange-rates');
        if (exchangeRatesElement) {
            const ratesHtml = Object.entries(data.rates).map(([currency, rate]) => `
                <div class="exchange-rate">
                    <span>1 EUR = ${rate.toFixed(4)} ${currency}</span>
                </div>
            `).join('');
            exchangeRatesElement.innerHTML = ratesHtml;
        }
    } catch (error) {
        console.error('Errore nel caricamento dei tassi:', error);
        const exchangeRatesElement = document.getElementById('exchange-rates');
        if (exchangeRatesElement) {
            exchangeRatesElement.innerHTML = 'Errore nel caricamento dei tassi di cambio';
        }
    }
}

// Conversione valuta
async function convertCurrency() {
    const amountInput = document.getElementById('amount-to-convert');
    const amount = parseFloat(amountInput.value);
    const toCurrency = document.getElementById('target-currency').value;
    const resultElement = document.getElementById('conversion-result');

    if (!amount || isNaN(amount)) {
        showError('Inserisci un importo valido');
        return;
    }

    try {
        const response = await fetch('/api/convert', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                amount: amount,
                to_currency: toCurrency
            })
        });

        const data = await response.json();
        if (data.error) {
            throw new Error(data.error);
        }

        resultElement.innerHTML = `
            <div>${data.amount} EUR = ${data.result} ${data.to}</div>
            <div class="conversion-rate">Tasso: ${data.rate}</div>
        `;
        resultElement.classList.add('show');
    } catch (error) {
        console.error('Errore nella conversione:', error);
        showError('Errore nella conversione della valuta');
    }
}

function initializeDashboard() {
    loadExchangeRates();
    setInterval(loadExchangeRates, 300000); // Aggiorna ogni 5 minuti
}

// Funzioni di utilità per i messaggi
function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-toast';
    errorDiv.textContent = message;
    document.body.appendChild(errorDiv);
    setTimeout(() => errorDiv.remove(), 3000);
}


// Funzione per mostrare messaggi di successo
function showSuccess(message) {
    const successDiv = document.createElement('div');
    successDiv.className = 'success-toast';
    successDiv.textContent = message;
    document.body.appendChild(successDiv);
    setTimeout(() => successDiv.remove(), 3000);
}