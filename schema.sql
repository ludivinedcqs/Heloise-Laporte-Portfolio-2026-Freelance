PRAGMA foreign_keys = ON;

-- USERS
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'client', -- 'client' ou 'admin'
    name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- PROJECTS / portfolio
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title_fr TEXT NOT NULL,
    title_en TEXT NOT NULL,
    title_es TEXT NOT NULL,
    description_fr TEXT NOT NULL,
    description_en TEXT NOT NULL,
    description_es TEXT NOT NULL,
    image TEXT,         -- chemin relatif vers static/images/...
    link TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- QUOTES (devis)
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    number TEXT NOT NULL,          -- numéro unique lisible
    amount REAL NOT NULL,
    date DATETIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- INVOICES (factures)
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    quote_id INTEGER,              -- optionnel : facture liée à un devis
    number TEXT NOT NULL,
    amount REAL NOT NULL,
    date DATETIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'unpaid',
    pdf_path TEXT,                 -- si tu sauves PDF sur disque
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE SET NULL
);

-- MESSAGES (messagerie interne)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    read INTEGER DEFAULT 0, -- 0 = non lu, 1 = lu
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
);

-- INDEXES utiles
CREATE INDEX IF NOT EXISTS idx_quotes_user ON quotes(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_user ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(sender_id, receiver_id, date);
