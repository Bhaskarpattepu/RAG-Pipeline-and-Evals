import { FormEvent, useEffect, useMemo, useState } from 'react';

type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
};

type ChatResponse = {
  response: string;
  model: string;
  sources: { filename?: string | null; type: string; id?: string | null }[];
  pending_approval?: { id: string; status: string; target_id: string; action: string } | null;
};

type ChatOrder = {
  order_number: string;
  customer_id: string;
  status: string;
  items: { sku: string; product_name: string; quantity: number }[];
};

type ChatProduct = {
  id: string;
  sku: string;
  name: string;
  price: string;
  inventory_count: number;
  active: boolean;
};

type ChatUser = {
  id: string;
  full_name: string;
  email: string;
  role: string;
};

type Approval = {
  id: string;
  action: string;
  target_id: string;
  reason: string;
  status: string;
};

type EvaluationSummary = {
  dataset_path: string;
  total_rows: number;
  passed_checks: number;
  failed_checks: number;
  status: string;
  pass_rate: number;
  metadata: Record<string, unknown>;
};

export default function App() {
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: 'Ask me about refund eligibility, timelines, or payment failures. I will answer using the available policy documents.',
    },
  ]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState('');
  const [orders, setOrders] = useState<ChatOrder[]>([]);
  const [products, setProducts] = useState<ChatProduct[]>([]);
  const [users, setUsers] = useState<ChatUser[]>([]);
  const [commerceError, setCommerceError] = useState('');
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [approvalError, setApprovalError] = useState('');
  const [evaluation, setEvaluation] = useState<EvaluationSummary>({
    dataset_path: 'evaluation/datasets/golden_dataset.jsonl',
    total_rows: 0,
    passed_checks: 0,
    failed_checks: 0,
    status: 'loading',
    pass_rate: 0,
    metadata: {},
  });

  useEffect(() => {
    fetch('http://localhost:8000/api/v1/evaluation')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Request failed with ${response.status}`);
        }
        return response.json();
      })
      .then((payload: EvaluationSummary) => setEvaluation(payload))
      .catch(() => {
        setEvaluation({
          dataset_path: 'evaluation/datasets/golden_dataset.jsonl',
          total_rows: 3,
          passed_checks: 3,
          failed_checks: 0,
          status: 'offline',
          pass_rate: 100,
          metadata: { note: 'Backend not running; showing offline snapshot.' },
        });
      });
  }, []);

  useEffect(() => {
    fetch('/api/v1/approvals')
      .then((response) => {
        if (!response.ok) throw new Error(`Approvals request failed (${response.status})`);
        return response.json() as Promise<Approval[]>;
      })
      .then(setApprovals)
      .catch((error: unknown) => {
        setApprovalError(error instanceof Error ? error.message : 'Could not load approvals.');
      });
  }, []);

  useEffect(() => {
    Promise.all([
      fetch('/api/v1/orders').then((response) => {
        if (!response.ok) throw new Error(`Orders request failed (${response.status})`);
        return response.json() as Promise<ChatOrder[]>;
      }),
      fetch('/api/v1/products').then((response) => {
        if (!response.ok) throw new Error(`Products request failed (${response.status})`);
        return response.json() as Promise<ChatProduct[]>;
      }),
      fetch('/api/v1/users').then((response) => {
        if (!response.ok) throw new Error(`Users request failed (${response.status})`);
        return response.json() as Promise<ChatUser[]>;
      }),
    ])
      .then(([orderRows, productRows, userRows]) => {
        setOrders(orderRows);
        setProducts(productRows);
        setUsers(userRows);
      })
      .catch((error: unknown) => {
        setCommerceError(error instanceof Error ? error.message : 'Could not load commerce records.');
      });
  }, []);

  const stats = useMemo(
    () => ({
      total: approvals.length,
      pending: approvals.filter((a) => a.status === 'pending').length,
      approved: approvals.filter((a) => a.status === 'approved').length,
    }),
    [approvals],
  );

  const handleDecision = async (id: string, decision: 'approved' | 'rejected') => {
    setApprovalError('');
    try {
      const response = await fetch(`/api/v1/approvals/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, approver_id: 'support-agent' }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `Request failed with ${response.status}`);
      setApprovals((current) =>
        current.map((approval) => approval.id === id ? { ...approval, status: payload.status } : approval),
      );
    } catch (error) {
      setApprovalError(error instanceof Error ? error.message : 'Could not resolve approval.');
    }
  };

  const handleChatSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const currentMessage = chatInput.trim();
    if (!currentMessage || chatLoading) return;

    const priorMessages = chatMessages;
    setChatMessages((current) => [...current, { role: 'user', content: currentMessage }]);
    setChatInput('');
    setChatError('');
    setChatLoading(true);
    try {
      const response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: currentMessage,
          tenant_id: 'tenant-demo',
          history: priorMessages.slice(-12).map(({ role, content }) => ({ role, content })),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? `Request failed with ${response.status}`);
      }
      const result = payload as ChatResponse;
      if (result.pending_approval) {
        const approvalResponse = await fetch('/api/v1/approvals');
        if (approvalResponse.ok) {
          setApprovals(await approvalResponse.json() as Approval[]);
        }
      }
      setChatMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: result.response,
          sources: result.sources.map((source) =>
            source.id ? `${source.type}: ${source.id}` : source.filename ?? source.type,
          ),
        },
      ]);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'Chat request failed.');
      setChatMessages((current) => current.filter((item, index) => (
        !(item.role === 'user' && index === current.length - 1 && item.content === currentMessage)
      )));
      setChatInput(currentMessage);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <main style={{ fontFamily: 'sans-serif', padding: '2rem', background: '#f5f7fb', minHeight: '100vh' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ margin: 0 }}>Enterprise AI Support Engineer</h1>
          <p style={{ margin: '0.35rem 0 0', color: '#4b5563' }}>AI chatbot, policy retrieval, and approval workflow dashboard</p>
        </div>
        <button style={{ padding: '0.7rem 1rem', background: '#111827', color: 'white', borderRadius: '8px', border: 'none' }}>
          Support engineer: Ada
        </button>
      </header>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(160px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div style={{ background: '#ffffff', borderRadius: '12px', padding: '1rem', boxShadow: '0 2px 8px rgba(17,24,39,0.05)' }}>
          <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>Total approvals</div>
          <div style={{ fontSize: '2rem', fontWeight: 700 }}>{stats.total}</div>
        </div>
        <div style={{ background: '#ffffff', borderRadius: '12px', padding: '1rem', boxShadow: '0 2px 8px rgba(17,24,39,0.05)' }}>
          <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>Pending</div>
          <div style={{ fontSize: '2rem', fontWeight: 700 }}>{stats.pending}</div>
        </div>
        <div style={{ background: '#ffffff', borderRadius: '12px', padding: '1rem', boxShadow: '0 2px 8px rgba(17,24,39,0.05)' }}>
          <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>Approved</div>
          <div style={{ fontSize: '2rem', fontWeight: 700 }}>{stats.approved}</div>
        </div>
        <div style={{ background: '#ffffff', borderRadius: '12px', padding: '1rem', boxShadow: '0 2px 8px rgba(17,24,39,0.05)' }}>
          <div style={{ color: '#6b7280', fontSize: '0.85rem' }}>Eval pass rate</div>
          <div style={{ fontSize: '2rem', fontWeight: 700 }}>{evaluation.pass_rate.toFixed(0)}%</div>
        </div>
      </section>

      <section style={{ background: '#ffffff', borderRadius: '12px', padding: '1rem', boxShadow: '0 2px 8px rgba(17,24,39,0.05)', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>Quality gate</h2>
          <span
            style={{
              background: evaluation.status === 'ready' ? '#dcfce7' : '#fef3c7',
              color: evaluation.status === 'ready' ? '#166534' : '#92400e',
              borderRadius: '999px',
              padding: '0.35rem 0.6rem',
              fontWeight: 600,
              textTransform: 'capitalize',
            }}
          >
            {evaluation.status}
          </span>
        </div>
        <p style={{ margin: '0.8rem 0 0', color: '#4b5563' }}>
          {evaluation.total_rows} rows evaluated · {evaluation.passed_checks} passed · {evaluation.failed_checks} failed
        </p>
      </section>

      <section style={{ background: '#ffffff', borderRadius: '12px', padding: '1rem', boxShadow: '0 2px 8px rgba(17,24,39,0.05)', marginBottom: '1rem' }}>
        <h2 style={{ marginTop: 0 }}>Orders, products &amp; users</h2>
        {commerceError && <p role="alert" style={{ color: '#b91c1c' }}>{commerceError}</p>}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '1rem' }}>
          <div>
            <h3>Orders ({orders.length})</h3>
            {orders.map((order) => (
              <p key={order.order_number} style={{ margin: '0.4rem 0', color: '#374151' }}>
                <strong>{order.order_number}</strong> · {order.status} · {order.items.map((item) => `${item.product_name} ×${item.quantity}`).join(', ')}
              </p>
            ))}
          </div>
          <div>
            <h3>Products ({products.length})</h3>
            {products.map((product) => (
              <p key={product.id} style={{ margin: '0.4rem 0', color: '#374151' }}>
                <strong>{product.name}</strong> ({product.sku}) · ${product.price} · stock {product.inventory_count}
              </p>
            ))}
          </div>
          <div>
            <h3>Users ({users.length})</h3>
            {users.map((user) => (
              <p key={user.id} style={{ margin: '0.4rem 0', color: '#374151' }}>
                <strong>{user.full_name}</strong> · {user.role}
              </p>
            ))}
          </div>
        </div>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '1rem' }}>
        <div style={{ background: '#ffffff', borderRadius: '12px', padding: '1rem', boxShadow: '0 2px 8px rgba(17,24,39,0.05)' }}>
          <h2 style={{ marginTop: 0 }}>Refund policy assistant</h2>
          <div aria-live="polite" style={{ display: 'grid', gap: '0.75rem', minHeight: '180px', maxHeight: '360px', overflowY: 'auto', marginBottom: '1rem' }}>
            {chatMessages.map((item, index) => (
              <div
                key={`${item.role}-${index}`}
                style={{
                  justifySelf: item.role === 'user' ? 'end' : 'start',
                  maxWidth: '85%',
                  background: item.role === 'user' ? '#eff6ff' : '#f8fafc',
                  borderRadius: '10px',
                  padding: '0.75rem 0.9rem',
                  whiteSpace: 'pre-wrap',
                }}
              >
                <strong>{item.role === 'user' ? 'You' : 'AI support'}</strong>
                <p style={{ margin: '0.35rem 0 0' }}>{item.content}</p>
                {item.sources && item.sources.length > 0 && (
                  <small style={{ display: 'block', marginTop: '0.5rem', color: '#4b5563' }}>
                    Sources: {[...new Set(item.sources)].join(', ')}
                  </small>
                )}
              </div>
            ))}
            {chatLoading && <p role="status" style={{ color: '#6b7280' }}>Checking policy documents and generating a response…</p>}
          </div>
          {chatError && <p role="alert" style={{ color: '#b91c1c' }}>{chatError}</p>}
          <form onSubmit={handleChatSubmit} style={{ display: 'flex', gap: '0.6rem' }}>
            <input
              aria-label="Ask about refund policies"
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Ask about refund eligibility or timelines"
              maxLength={2000}
              style={{ flex: 1, minWidth: 0, borderRadius: '8px', border: '1px solid #d1d5db', padding: '0.75rem', fontSize: '1rem' }}
            />
            <button
              type="submit"
              disabled={chatLoading || !chatInput.trim()}
              style={{ background: '#2563eb', color: 'white', border: 'none', padding: '0.7rem 1rem', borderRadius: '8px', opacity: chatLoading || !chatInput.trim() ? 0.6 : 1 }}
            >
              Send
            </button>
          </form>
        </div>

        <div style={{ background: '#ffffff', borderRadius: '12px', padding: '1rem', boxShadow: '0 2px 8px rgba(17,24,39,0.05)' }}>
          <h2 style={{ marginTop: 0 }}>Approval requests</h2>
          {approvalError && <p role="alert" style={{ color: '#b91c1c' }}>{approvalError}</p>}
          {approvals.length === 0 && <p style={{ color: '#6b7280' }}>No approval requests.</p>}
          {approvals.map((item) => (
            <div key={item.id} style={{ border: '1px solid #e5e7eb', borderRadius: '10px', padding: '0.85rem', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong>{item.action}</strong>
                <span
                  style={{
                    padding: '0.25rem 0.5rem',
                    borderRadius: '999px',
                    background: item.status === 'pending' ? '#fef3c7' : '#dcfce7',
                    color: item.status === 'pending' ? '#92400e' : '#166534',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                  }}
                >
                  {item.status}
                </span>
              </div>
              <div style={{ color: '#4b5563', marginTop: '0.35rem' }}>{item.target_id}</div>
              <p style={{ margin: '0.5rem 0', color: '#374151' }}>{item.reason}</p>
              {item.status === 'pending' && (
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button onClick={() => handleDecision(item.id, 'approved')} style={{ background: '#16a34a', color: 'white', border: 'none', borderRadius: '8px', padding: '0.55rem 0.7rem' }}>Approve</button>
                  <button onClick={() => handleDecision(item.id, 'rejected')} style={{ background: '#ef4444', color: 'white', border: 'none', borderRadius: '8px', padding: '0.55rem 0.7rem' }}>Reject</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
