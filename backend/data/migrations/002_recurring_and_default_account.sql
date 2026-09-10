-- Migration 002: Recurring Transactions & Default Account Flag
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS recurring_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL DEFAULT 'default_user',
    name TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense', 'transfer')),
    category TEXT,
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    to_account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly')),
    day_of_month INT,
    day_of_week INT,
    start_date DATE NOT NULL DEFAULT CURRENT_DATE,
    end_date DATE,
    next_due_date DATE NOT NULL,
    last_executed_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    auto_execute BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE recurring_transactions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'recurring_transactions' AND policyname = 'Allow all operations for recurring_transactions') THEN
        CREATE POLICY "Allow all operations for recurring_transactions" ON recurring_transactions FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;
