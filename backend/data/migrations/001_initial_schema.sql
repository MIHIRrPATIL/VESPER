-- ==============================================================================
-- VESPER Supabase Initial Schema (001_initial_schema.sql)
-- ==============================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. Tasks Table
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL DEFAULT 'default_user',
    title TEXT NOT NULL,
    deadline TIMESTAMPTZ,
    done BOOLEAN DEFAULT FALSE,
    priority TEXT DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Accounts Table (Personal Finance)
CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL DEFAULT 'default_user',
    name TEXT NOT NULL,
    type TEXT DEFAULT 'bank' CHECK (type IN ('bank', 'cash', 'credit', 'wallet')),
    balance NUMERIC(12, 2) DEFAULT 0.00,
    currency TEXT DEFAULT 'INR',
    metadata JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, name)
);

-- 4. Transactions Table (Double-Entry Ledger)
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL DEFAULT 'default_user',
    type TEXT NOT NULL CHECK (type IN ('income', 'expense', 'transfer')),
    amount NUMERIC(12, 2) NOT NULL,
    category TEXT,
    description TEXT,
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    to_account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Debts Table (Peer-to-Peer Owe / Owed)
CREATE TABLE IF NOT EXISTS debts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL DEFAULT 'default_user',
    person TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('owe', 'owed')),
    description TEXT,
    settled BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    settled_at TIMESTAMPTZ
);

-- 6. Shodh-Memory Table (Episodic Learned Facts & Experiences)
CREATE TABLE IF NOT EXISTS shodh_memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL DEFAULT 'default_user',
    statement TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    confidence REAL DEFAULT 1.0,
    access_count INT DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. High-Performance Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_user_done ON tasks(user_id, done);
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date);
CREATE INDEX IF NOT EXISTS idx_debts_user_settled ON debts(user_id, settled);
CREATE INDEX IF NOT EXISTS idx_memories_user_category ON shodh_memories(user_id, category);

-- 8. Permissive RLS Policies (for initial dev)
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE debts ENABLE ROW LEVEL SECURITY;
ALTER TABLE shodh_memories ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'tasks' AND policyname = 'Allow all operations for tasks') THEN
        CREATE POLICY "Allow all operations for tasks" ON tasks FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'accounts' AND policyname = 'Allow all operations for accounts') THEN
        CREATE POLICY "Allow all operations for accounts" ON accounts FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'transactions' AND policyname = 'Allow all operations for transactions') THEN
        CREATE POLICY "Allow all operations for transactions" ON transactions FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'debts' AND policyname = 'Allow all operations for debts') THEN
        CREATE POLICY "Allow all operations for debts" ON debts FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'shodh_memories' AND policyname = 'Allow all operations for shodh_memories') THEN
        CREATE POLICY "Allow all operations for shodh_memories" ON shodh_memories FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;
