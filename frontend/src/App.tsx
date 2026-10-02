import {
  useEffect,
  useState,
  useCallback,
  useRef,
  FormEvent,
  ReactNode,
} from "react";
import {
  Activity,
  LayoutDashboard,
  ShoppingCart,
  Pill,
  Boxes,
  PackagePlus,
  SlidersHorizontal,
  Truck,
  Users,
  ReceiptText,
  ChartNoAxesCombined,
  ShieldCheck,
  Settings,
  LogOut,
  Search,
  Plus,
  Printer,
  Download,
  X,
  Menu,
  ArrowUpRight,
  CheckCircle2,
  AlertTriangle,
  Trash2,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar,
} from "recharts";
import { api, setToken, download } from "./api";
type Row = Record<string, any>;
type Field = {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
  min?: number;
  step?: string;
};
const nav = [
  ["Dashboard", LayoutDashboard],
  ["New sale", ShoppingCart],
  ["Products", Pill],
  ["Inventory", Boxes],
  ["Receive stock", PackagePlus],
  ["Adjustments", SlidersHorizontal],
  ["Suppliers", Truck],
  ["Customers", Users],
  ["Sales", ReceiptText],
  ["Reports", ChartNoAxesCombined],
  ["Users", ShieldCheck],
  ["Audit log", ShieldCheck],
  ["Settings", Settings],
] as const;
const adminPages = ["Adjustments", "Users", "Audit log", "Settings", "Reports"];
const cashierPages = ["Dashboard", "New sale", "Products", "Sales"];
let displayCurrency = "GHS";
const fmt = (n: any, currency = displayCurrency) =>
  new Intl.NumberFormat("en-GH", { style: "currency", currency }).format(
    Number(n || 0),
  );
const dateText = (v: any) =>
  v
    ? new Date(
        v.endsWith("Z") || /[+-]\d\d:\d\d$/.test(v) ? v : v + "Z",
      ).toLocaleString("en-GB", { timeZone: "Africa/Accra" })
    : "—";
const columns: Record<string, [string, string][]> = {
  Products: [
    ["name", "Product"],
    ["code", "Code"],
    ["category", "Category"],
    ["selling_price", "Price"],
    ["quantity", "Sellable stock"],
    ["reorder_level", "Reorder level"],
    ["next_expiry", "Next expiry"],
  ],
  Inventory: [
    ["product_name", "Product"],
    ["number", "Batch"],
    ["quantity", "Quantity"],
    ["purchase_price", "Unit cost"],
    ["expiry_date", "Expiry"],
    ["expired", "Expired"],
  ],
  Suppliers: [
    ["name", "Supplier"],
    ["contact", "Contact"],
    ["phone", "Phone"],
    ["email", "Email"],
    ["deliveries", "Deliveries"],
    ["purchased_value", "Purchased value"],
  ],
  Customers: [
    ["name", "Customer"],
    ["phone", "Phone"],
    ["email", "Email"],
  ],
  Sales: [
    ["receipt_number", "Receipt"],
    ["created_at", "Date"],
    ["cashier", "Staff"],
    ["payment_method", "Payment"],
    ["total", "Total"],
    ["status", "Status"],
  ],
  Users: [
    ["username", "Username"],
    ["email", "Email"],
    ["role", "Role"],
    ["active", "Active"],
  ],
  "Audit log": [
    ["created_at", "Date"],
    ["username", "User"],
    ["action", "Action"],
    ["record", "Record"],
    ["detail", "Details"],
  ],
  Movements: [
    ["created_at", "Date"],
    ["product_name", "Product"],
    ["batch_number", "Batch"],
    ["kind", "Movement"],
    ["quantity", "Change"],
    ["reference", "Reference"],
    ["reason", "Reason"],
  ],
  Receipts: [
    ["created_at", "Received"],
    ["supplier_name", "Supplier"],
    ["reference", "Invoice/reference"],
    ["notes", "Notes"],
  ],
};
function Table({
  rows,
  cols,
  onRow,
  action,
}: {
  rows: Row[];
  cols: [string, string][];
  onRow?: (r: Row) => void;
  action?: (r: Row) => ReactNode;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {cols.map(([k, l]) => (
              <th key={k}>{l}</th>
            ))}
            {action && <th>Action</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={r.id || i}
              className={onRow ? "clickable" : ""}
              onClick={() => onRow?.(r)}
            >
              {cols.map(([k]) => (
                <td key={k}>
                  {typeof r[k] === "boolean" ? (
                    <span className={"tag " + (r[k] ? "teal" : "muted")}>
                      {r[k] ? "Yes" : "No"}
                    </span>
                  ) : k === "status" ? (
                    <span
                      className={
                        "tag " + (r[k] === "completed" ? "teal" : "amber")
                      }
                    >
                      {r[k]}
                    </span>
                  ) : [
                      "selling_price",
                      "purchase_price",
                      "total",
                      "sales",
                      "purchased_value",
                    ].includes(k) ? (
                    fmt(r[k])
                  ) : k === "created_at" ? (
                    dateText(r[k])
                  ) : typeof r[k] === "object" && r[k] !== null ? (
                    JSON.stringify(r[k])
                  ) : (
                    String(r[k] ?? "—")
                  )}
                </td>
              ))}
              {action && (
                <td onClick={(e) => e.stopPropagation()}>{action(r)}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && (
        <div className="empty">
          <Boxes size={30} />
          <p>No records to display.</p>
          <small>Add records or adjust your filters.</small>
        </div>
      )}
    </div>
  );
}
function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  return (
    <div className="overlay" role="presentation">
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <h2>{title}</h2>
          <button className="icon" aria-label="Close dialog" onClick={close}>
            <X />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
function Form({
  fields,
  initial = {},
  submit,
  label = "Save",
  busy = false,
}: {
  fields: Field[];
  initial?: Row;
  submit: (data: Row) => void;
  label?: string;
  busy?: boolean;
}) {
  const [values, setValues] = useState<Row>(initial);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit(values);
      }}
    >
      <div className="form-grid">
        {fields.map((f) => (
          <label key={f.key}>
            {f.label}
            {f.type === "checkbox" ? (
              <input
                type="checkbox"
                checked={!!values[f.key]}
                onChange={(e) =>
                  setValues({ ...values, [f.key]: e.target.checked })
                }
              />
            ) : f.options ? (
              <select
                value={values[f.key] ?? ""}
                required={f.required}
                onChange={(e) =>
                  setValues({ ...values, [f.key]: e.target.value })
                }
              >
                <option value="">Select…</option>
                {f.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : f.type === "textarea" ? (
              <textarea
                required={f.required}
                value={values[f.key] ?? ""}
                onChange={(e) =>
                  setValues({ ...values, [f.key]: e.target.value })
                }
              />
            ) : (
              <input
                type={f.type || "text"}
                required={f.required}
                min={f.min}
                step={f.step}
                value={values[f.key] ?? ""}
                onChange={(e) =>
                  setValues({
                    ...values,
                    [f.key]:
                      f.type === "number"
                        ? Number(e.target.value)
                        : e.target.value,
                  })
                }
              />
            )}
          </label>
        ))}
      </div>
      <button className="primary" disabled={busy} type="submit">
        {busy ? "Saving…" : label}
      </button>
    </form>
  );
}
const productFields: Field[] = [
  { key: "name", label: "Brand/product name", required: true },
  { key: "code", label: "Product code", required: true },
  { key: "barcode", label: "Barcode" },
  { key: "generic_name", label: "Generic name" },
  { key: "strength", label: "Strength" },
  { key: "form", label: "Dosage form" },
  { key: "pack_size", label: "Pack size / sale unit" },
  { key: "category", label: "Category", required: true },
  { key: "manufacturer", label: "Manufacturer" },
  {
    key: "selling_price",
    label: "Selling price (GHS)",
    type: "number",
    min: 0,
    step: ".01",
    required: true,
  },
  {
    key: "reorder_level",
    label: "Reorder level",
    type: "number",
    min: 0,
    required: true,
  },
  {
    key: "prescription_required",
    label: "Prescription required",
    type: "checkbox",
  },
  { key: "storage_notes", label: "Storage notes", type: "textarea" },
];
const supplierFields: Field[] = [
  { key: "name", label: "Supplier name", required: true },
  { key: "contact", label: "Contact person" },
  { key: "phone", label: "Phone" },
  { key: "email", label: "Email", type: "email" },
  { key: "address", label: "Address", type: "textarea" },
];
const customerFields: Field[] = [
  { key: "name", label: "Customer name", required: true },
  { key: "phone", label: "Phone" },
  { key: "email", label: "Email", type: "email" },
];
function Login({
  onLogin,
  notify,
}: {
  onLogin: (u: Row) => void;
  notify: (s: string, error?: boolean) => void;
}) {
  const [mode, setMode] = useState("login");
  const [busy, setBusy] = useState(false);
  async function submit(values: Row) {
    setBusy(true);
    try {
      if (mode === "login") {
        const result = await api("/auth/login", "POST", values);
        setToken(result.access_token);
        onLogin(result.user);
      } else {
        const result = await api(
          "/auth/" + (mode === "request" ? "reset-request" : "reset-confirm"),
          "POST",
          values,
        );
        notify(result.message);
        if (mode === "confirm") setMode("login");
      }
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <div className="login-story">
        <div className="brand">
          <span>
            <Activity />
          </span>
          PharmaStock<span className="pos">POS</span>
        </div>
        <div>
          <span className="eyebrow">YOUR PHARMACY, IN SYNC</span>
          <h1>
            Better stock.
            <br />
            Smoother sales.
            <br />
            More time for care.
          </h1>
          <p>
            A clear view of your pharmacy, from the next delivery to the last
            receipt of the day.
          </p>
          <div className="story-features">
            <span>
              <CheckCircle2 />
              Batch & expiry tracking
            </span>
            <span>
              <CheckCircle2 />
              Fast, accurate checkout
            </span>
            <span>
              <CheckCircle2 />
              Secure staff access
            </span>
          </div>
        </div>
        <small>Built for everyday pharmacy operations.</small>
      </div>
      <section className="login-box">
        <div className="mini-mark">
          <Pill size={28} />
        </div>
        <h2>
          {mode === "login"
            ? "Welcome back"
            : mode === "request"
              ? "Forgot your password?"
              : "Set a new password"}
        </h2>
        <p>
          {mode === "login"
            ? "Sign in to your pharmacy workspace."
            : "Your administrator can help if email is not configured."}
        </p>
        <Form
          key={mode}
          busy={busy}
          submit={submit}
          label={mode === "login" ? "Sign in to workspace" : "Continue"}
          fields={
            mode === "login"
              ? [
                  {
                    key: "username",
                    label: "Username or email",
                    required: true,
                  },
                  {
                    key: "password",
                    label: "Password",
                    type: "password",
                    required: true,
                  },
                ]
              : mode === "request"
                ? [
                    {
                      key: "email",
                      label: "Account email",
                      type: "email",
                      required: true,
                    },
                  ]
                : [
                    {
                      key: "token",
                      label: "Reset token from email",
                      required: true,
                    },
                    {
                      key: "password",
                      label: "New password (12+ characters)",
                      type: "password",
                      required: true,
                    },
                  ]
          }
        />
        <div className="login-links">
          <button
            className="link"
            onClick={() => setMode(mode === "login" ? "request" : "login")}
          >
            {mode === "login" ? "Forgot password?" : "Back to sign in"}
          </button>
          {mode === "request" && (
            <button className="link" onClick={() => setMode("confirm")}>
              I have a reset token
            </button>
          )}
        </div>
        <div className="secure-note">
          <ShieldCheck size={17} /> Authorized pharmacy staff only
        </div>
      </section>
    </div>
  );
}
export default function App() {
  const [user, setUser] = useState<Row | null>(null),
    [page, setPage] = useState("Dashboard"),
    [mobile, setMobile] = useState(false),
    [toast, setToast] = useState<{ message: string; error: boolean } | null>(
      null,
    ),
    [config, setConfig] = useState<Row>({
      currency: "GHS",
      payment_methods: ["Cash", "Mobile Money", "Card"],
      tax_percent: 0,
    }),
    [receipt, setReceipt] = useState<Row | null>(null);
  const notify = useCallback((message: string, error = false) => {
    setToast({ message, error });
  }, []);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 8000);
      return () => clearTimeout(t);
    }
  }, [toast]);
  useEffect(() => {
    const expire = () => {
      setUser(null);
      setToken("");
      setReceipt(null);
    };
    window.addEventListener("session-expired", expire);
    return () => window.removeEventListener("session-expired", expire);
  }, []);
  const idle = useRef(Date.now());
  useEffect(() => {
    if (!user) return;
    const activity = () => {
      idle.current = Date.now();
    };
    window.addEventListener("pointerdown", activity);
    window.addEventListener("keydown", activity);
    const timer = setInterval(() => {
      if (Date.now() - idle.current > 15 * 60 * 1000) {
        api("/auth/logout", "POST").catch(() => {});
        setUser(null);
        setToken("");
        notify("Signed out after 15 minutes of inactivity.");
      }
    }, 10000);
    api("/settings")
      .then(setConfig)
      .catch((e) => notify(e.message, true));
    return () => {
      clearInterval(timer);
      window.removeEventListener("pointerdown", activity);
      window.removeEventListener("keydown", activity);
    };
  }, [user, notify]);
  async function signout() {
    try {
      await api("/auth/logout", "POST");
    } catch {}
    setUser(null);
    setToken("");
    setReceipt(null);
    setPage("Dashboard");
  }
  displayCurrency = config.currency || "GHS";
  const permitted = nav.filter(([name]) =>
    user?.role === "cashier"
      ? cashierPages.includes(name)
      : user?.role === "pharmacist"
        ? !adminPages.includes(name)
        : true,
  );
  return (
    <>
      {toast && (
        <div role="status" className={"toast " + (toast.error ? "error" : "")}>
          <span>
            {toast.error ? (
              <AlertTriangle size={18} />
            ) : (
              <CheckCircle2 size={18} />
            )}
          </span>
          {toast.message}
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {!user ? (
        <Login
          notify={notify}
          onLogin={(u) => {
            idle.current = Date.now();
            setUser(u);
            setPage("Dashboard");
          }}
        />
      ) : (
        <div className="app">
          <aside className={mobile ? "sidebar open" : "sidebar"}>
            <div className="brand">
              <span>
                <Activity />
              </span>
              PharmaStock<span className="pos">POS</span>
            </div>
            <p className="sidebar-caption">PHARMACY WORKSPACE</p>
            <nav>
              {permitted.map(([name, Icon]) => (
                <button
                  key={name}
                  className={page === name ? "active" : ""}
                  onClick={() => {
                    setPage(name);
                    setMobile(false);
                  }}
                >
                  <Icon size={19} />
                  {name}
                  {name === "New sale" && <span className="nav-plus">+</span>}
                </button>
              ))}
            </nav>
            <div className="sidebar-bottom">
              <div className="avatar">
                {String(user.username).slice(0, 2).toUpperCase()}
              </div>
              <div>
                <strong>{user.username}</strong>
                <small>{user.role}</small>
              </div>
              <button className="icon" aria-label="Sign out" onClick={signout}>
                <LogOut size={19} />
              </button>
            </div>
          </aside>
          {mobile && (
            <div className="sidebar-shade" onClick={() => setMobile(false)} />
          )}
          <div className="workspace">
            <header className="topbar">
              <button
                className="icon mobile-menu"
                aria-label="Open navigation"
                onClick={() => setMobile(true)}
              >
                <Menu />
              </button>
              <div>
                <span>Workspace</span>
                <b>/</b>
                <strong>{page}</strong>
              </div>
              <div className="topbar-right">
                <span className="live-dot" />{" "}
                {config.pharmacy_name || "PharmaStock Pharmacy"}{" "}
                <span className="tag muted">{config.currency}</span>
              </div>
            </header>
            <main>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">PHARMASTOCK POS</span>
                  <h1>
                    {page === "Dashboard" ? "Your pharmacy at a glance" : page}
                  </h1>
                  <p>
                    {
                      (
                        {
                          Dashboard:
                            "Keep stock healthy and your day running smoothly.",
                          "New sale":
                            "Find products, complete a sale, and print a receipt.",
                          Products:
                            "Your medicine and healthcare product catalogue.",
                          Inventory:
                            "Track every batch and stay ahead of expiry dates.",
                          "Receive stock":
                            "Record deliveries and add stock without losing the history.",
                          Adjustments:
                            "Keep stock counts accurate with a recorded reason.",
                          Suppliers:
                            "Your supply partners and delivery history.",
                          Customers:
                            "Optional customer records, protected by staff permissions.",
                          Sales: "Review transactions and reprint receipts.",
                          Reports:
                            "Understand sales, margins, and stock value.",
                          Users: "Manage staff access to your pharmacy.",
                          "Audit log":
                            "A traceable history of important system actions.",
                          Settings:
                            "Configure your pharmacy and checkout preferences.",
                        } as Row
                      )[page]
                    }
                  </p>
                </div>
                <span className="date-pill">
                  {new Date().toLocaleDateString("en-GB", {
                    timeZone: "Africa/Accra",
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
              </div>
              {page === "Dashboard" ? (
                <Dashboard notify={notify} config={config} navigate={setPage} />
              ) : page === "New sale" ? (
                <POS
                  user={user}
                  config={config}
                  notify={notify}
                  complete={setReceipt}
                />
              ) : page === "Receive stock" ? (
                <Receive notify={notify} />
              ) : page === "Adjustments" ? (
                <Adjust notify={notify} />
              ) : page === "Reports" ? (
                <Reports notify={notify} />
              ) : page === "Settings" ? (
                <SettingsPage
                  config={config}
                  onChange={setConfig}
                  notify={notify}
                />
              ) : (
                <Records
                  key={page}
                  page={page}
                  user={user}
                  notify={notify}
                  receipt={setReceipt}
                  defaultReorder={config.default_reorder_level ?? 20}
                />
              )}
            </main>
            <footer>
              PharmaStock POS{" "}
              <span>Inventory precision. Everyday confidence.</span>
            </footer>
          </div>
        </div>
      )}
      {receipt && (
        <Receipt
          sale={receipt}
          close={() => setReceipt(null)}
          notify={notify}
          admin={user?.role === "admin"}
        />
      )}
    </>
  );
}
function Dashboard({
  notify,
  config,
  navigate,
}: {
  notify: Function;
  config: Row;
  navigate: (p: string) => void;
}) {
  const [data, setData] = useState<Row | null>(null);
  useEffect(() => {
    api("/dashboard")
      .then(setData)
      .catch((e) => notify(e.message, true));
  }, [notify]);
  if (!data) return <div className="loading">Loading pharmacy overview…</div>;
  const cards = [
    [
      "Sales today",
      fmt(data.today_sales, config.currency),
      ReceiptText,
      "teal",
    ],
    ["Transactions", data.today_transactions, ShoppingCart, "blue"],
    ["Products in stock", data.in_stock, Boxes, "purple"],
    ["Low-stock products", data.low_stock, AlertTriangle, "amber"],
  ];
  return (
    <>
      <div className="stats">
        {cards.map(([label, value, Icon, color]: any) => (
          <section className="stat" key={label}>
            <div className="stat-top">
              <span>{label}</span>
              <div className={"stat-icon " + color}>
                <Icon size={21} />
              </div>
            </div>
            <strong>{value}</strong>
            <small>
              {label === "Sales today"
                ? "Completed sales, excluding refunds"
                : label === "Low-stock products"
                  ? "At or below reorder level"
                  : "Current pharmacy activity"}
            </small>
          </section>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Sales performance</h2>
              <p>Daily revenue over the last 30 days</p>
            </div>
            <span className="tag teal">Last 30 days</span>
          </div>
          <div className="chart">
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={data.trend}>
                <defs>
                  <linearGradient id="salesFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0d8b7d" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#0d8b7d" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(v) => v.slice(5)}
                  minTickGap={30}
                />
                <YAxis width={45} />
                <Tooltip formatter={(v) => fmt(v, config.currency)} />
                <Area
                  type="monotone"
                  dataKey="sales"
                  stroke="#0d8b7d"
                  strokeWidth={3}
                  fill="url(#salesFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Stock health</h2>
              <p>Stay a step ahead</p>
            </div>
            <Boxes size={20} />
          </div>
          <div className="health-row">
            <span>
              <i className="dot teal" />
              Total products
            </span>
            <strong>{data.total_products}</strong>
          </div>
          <div className="health-row">
            <span>
              <i className="dot blue" />
              Available products
            </span>
            <strong>{data.in_stock}</strong>
          </div>
          <div className="health-row">
            <span>
              <i className="dot amber" />
              Out of stock
            </span>
            <strong>{data.out_of_stock}</strong>
          </div>
          <div className="health-row">
            <span>
              <i className="dot purple" />
              Expiring soon
            </span>
            <strong>{data.expiring}</strong>
          </div>
          <div className="health-row">
            <span>
              <i className="dot red" />
              Expired stock
            </span>
            <strong>{data.expired}</strong>
          </div>
          <button
            className="link stock-link"
            onClick={() => navigate("Products")}
          >
            View product catalogue <ArrowUpRight size={17} />
          </button>
        </section>
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Needs your attention</h2>
              <p>Reorder and expiry alerts</p>
            </div>
            <span className="tag amber">{data.alerts.length} alerts</span>
          </div>
          {data.alerts.length ? (
            data.alerts.map((p: Row) => (
              <div className="alert-row" key={p.id}>
                <div className="product-symbol">
                  <Pill size={20} />
                </div>
                <div>
                  <strong>{p.name}</strong>
                  <small>
                    {p.strength} · {p.quantity} sellable units
                  </small>
                </div>
                <span
                  className={
                    "tag " +
                    (p.expired_quantity
                      ? "red"
                      : p.quantity <= p.reorder_level
                        ? "amber"
                        : "purple")
                  }
                >
                  {p.expired_quantity
                    ? "Expired batch"
                    : p.quantity === 0
                      ? "Out of stock"
                      : p.quantity <= p.reorder_level
                        ? "Low stock"
                        : "Expiring soon"}
                </span>
              </div>
            ))
          ) : (
            <div className="empty">All clear. No stock alerts.</div>
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Top-selling products</h2>
              <p>Units sold over the last 30 days</p>
            </div>
            <ChartNoAxesCombined size={20} />
          </div>
          {data.best_sellers.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart
                data={data.best_sellers}
                layout="vertical"
                margin={{ left: 20, right: 25 }}
              >
                <XAxis type="number" />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={115}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip />
                <Bar dataKey="quantity" fill="#0d8b7d" radius={[0, 5, 5, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty">
              <ShoppingCart size={30} />
              <p>Your sales story starts with the first checkout.</p>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
function POS({
  user,
  config,
  notify,
  complete,
}: {
  user: Row;
  config: Row;
  notify: Function;
  complete: (s: Row) => void;
}) {
  const [q, setQ] = useState(""),
    [products, setProducts] = useState<Row[]>([]),
    [cart, setCart] = useState<Row[]>([]),
    [discount, setDiscount] = useState(0),
    [method, setMethod] = useState("Cash"),
    [paid, setPaid] = useState(""),
    [verified, setVerified] = useState(false),
    [busy, setBusy] = useState(false),
    [customers, setCustomers] = useState<Row[]>([]),
    [customer, setCustomer] = useState("");
  const requestKey = useRef(crypto.randomUUID());
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api("/products?limit=50&q=" + encodeURIComponent(q))
        .then((d) => {
          if (live) setProducts(d.items);
        })
        .catch((e) => notify(e.message, true));
    }, 150);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [q, notify]);
  useEffect(() => {
    if (user.role !== "cashier")
      api("/customers")
        .then(setCustomers)
        .catch((e) => notify(e.message, true));
  }, [user.role, notify]);
  function add(p: Row) {
    if (p.quantity < 1) {
      notify("This product has no sellable stock.", true);
      return;
    }
    if (p.prescription_required && user.role === "cashier") {
      notify("A pharmacist must process this prescription product.", true);
      return;
    }
    setCart((old) => {
      const exists = old.find((i) => i.id === p.id);
      if (exists && exists.qty >= p.quantity) {
        notify("Available stock limit reached.", true);
        return old;
      }
      return exists
        ? old.map((i) => (i.id === p.id ? { ...i, qty: i.qty + 1 } : i))
        : [...old, { ...p, qty: 1 }];
    });
    requestKey.current = crypto.randomUUID();
  }
  const subtotalCents = cart.reduce(
      (s, p) => s + Math.round(p.selling_price * 100) * p.qty,
      0,
    ),
    discountCents = Math.round(discount * 100),
    taxCents = Math.round(
      ((subtotalCents - discountCents) * Number(config.tax_percent)) / 100,
    ),
    total = Math.max(0, (subtotalCents - discountCents + taxCents) / 100);
  async function checkout() {
    if (!cart.length) return;
    setBusy(true);
    try {
      const sale = await api("/sales", "POST", {
        items: cart.map((p) => ({ product_id: p.id, quantity: p.qty })),
        discount,
        payment_method: method,
        amount_paid: paid === "" ? total : Number(paid),
        customer_id: customer ? Number(customer) : null,
        prescription_verified: verified,
        idempotency_key: requestKey.current,
      });
      complete(sale);
      setCart([]);
      setPaid("");
      setDiscount(0);
      setVerified(false);
      setCustomer("");
      requestKey.current = crypto.randomUUID();
      const result = await api("/products?limit=50&q=" + encodeURIComponent(q));
      setProducts(result.items);
      notify("Sale completed. Receipt is ready.");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="pos-grid">
      <section className="panel product-picker">
        <div className="panel-heading">
          <h2>Find a product</h2>
          <span className="tag muted">Barcode ready</span>
        </div>
        <div className="search-field">
          <Search size={18} />
          <input
            aria-label="Search products or scan barcode"
            placeholder="Name, generic name or barcode…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const p =
                  products.find((p) => p.barcode === q || p.code === q) ||
                  (products.length === 1 ? products[0] : null);
                if (p) {
                  add(p);
                  setQ("");
                }
              }
            }}
            autoFocus
          />
        </div>
        <div className="product-list">
          {products.map((p) => (
            <button
              className="product-card"
              key={p.id}
              onClick={() => add(p)}
              disabled={!p.quantity || busy}
            >
              <div className="product-symbol">
                <Pill size={20} />
              </div>
              <div>
                <strong>{p.name}</strong>
                <small>
                  {p.strength} · {p.form}
                </small>
                <span
                  className={
                    "tag " + (p.quantity <= p.reorder_level ? "amber" : "teal")
                  }
                >
                  {p.quantity} in stock
                </span>
                {p.prescription_required && (
                  <span className="tag purple">Rx</span>
                )}
              </div>
              <b>{fmt(p.selling_price, config.currency)}</b>
              <Plus size={17} />
            </button>
          ))}
          {!products.length && (
            <div className="empty">No products match your search.</div>
          )}
        </div>
      </section>
      <section className="panel cart-panel">
        <div className="panel-heading">
          <h2>Current sale</h2>
          <span className="tag muted">
            {cart.reduce((s, p) => s + p.qty, 0)} items
          </span>
        </div>
        {cart.length ? (
          <div className="cart-items">
            {cart.map((p) => (
              <div className="cart-item" key={p.id}>
                <div>
                  <strong>{p.name}</strong>
                  <small>
                    {fmt(p.selling_price, config.currency)} /{" "}
                    {p.pack_size || "unit"}
                  </small>
                </div>
                <input
                  aria-label={"Quantity for " + p.name}
                  type="number"
                  min="1"
                  max={p.quantity}
                  value={p.qty}
                  disabled={busy}
                  onChange={(e) => {
                    const qty = Math.max(
                      1,
                      Math.min(p.quantity, Number(e.target.value) || 1),
                    );
                    setCart(
                      cart.map((i) => (i.id === p.id ? { ...i, qty } : i)),
                    );
                    requestKey.current = crypto.randomUUID();
                  }}
                />
                <b>{fmt(p.selling_price * p.qty, config.currency)}</b>
                <button
                  className="icon danger"
                  disabled={busy}
                  aria-label={"Remove " + p.name}
                  onClick={() => {
                    setCart(cart.filter((i) => i.id !== p.id));
                    requestKey.current = crypto.randomUUID();
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty cart-empty">
            <ShoppingCart size={40} />
            <h3>Ready for the next customer</h3>
            <p>Add a product to start a sale.</p>
          </div>
        )}
        {cart.some((p) => p.prescription_required) && (
          <label className="check-line">
            <input
              type="checkbox"
              checked={verified}
              disabled={busy}
              onChange={(e) => setVerified(e.target.checked)}
            />
            I have professionally verified the prescription.
          </label>
        )}
        {user.role !== "cashier" && (
          <label className="customer-select">
            Customer (optional)
            <select
              value={customer}
              disabled={busy}
              onChange={(e) => setCustomer(e.target.value)}
            >
              <option value="">Walk-in customer</option>
              {customers.map((c) => (
                <option value={c.id} key={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </section>
      <section className="panel checkout">
        <div className="panel-heading">
          <h2>Payment summary</h2>
        </div>
        <div className="summary-row">
          <span>Subtotal</span>
          <strong>{fmt(subtotalCents / 100, config.currency)}</strong>
        </div>
        <label>
          Discount ({config.currency})
          <input
            type="number"
            min="0"
            max={subtotalCents / 100}
            step=".01"
            value={discount}
            disabled={user.role === "cashier" || busy}
            onChange={(e) => setDiscount(Number(e.target.value))}
          />
        </label>
        <div className="summary-row">
          <span>Tax ({config.tax_percent}%)</span>
          <strong>{fmt(taxCents / 100, config.currency)}</strong>
        </div>
        <div className="total-row">
          <span>Total due</span>
          <strong>{fmt(total, config.currency)}</strong>
        </div>
        <label>
          Payment method
          <select
            value={method}
            disabled={busy}
            onChange={(e) => {
              setMethod(e.target.value);
              setPaid("");
            }}
          >
            {config.payment_methods.map((m: string) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </label>
        <label>
          Amount paid
          <input
            type="number"
            min="0"
            step=".01"
            placeholder={total.toFixed(2)}
            value={paid}
            disabled={busy}
            onChange={(e) => setPaid(e.target.value)}
          />
        </label>
        <div className="summary-row">
          <span>Change</span>
          <strong>
            {fmt(Math.max(0, Number(paid || total) - total), config.currency)}
          </strong>
        </div>
        <button
          className="primary checkout-button"
          disabled={!cart.length || busy}
          onClick={checkout}
        >
          <CheckCircle2 size={19} />
          {busy ? "Completing sale…" : "Complete sale"}
        </button>
        <p className="secure-note">
          <ShieldCheck size={16} />
          Stock updates after a successful sale.
        </p>
      </section>
    </div>
  );
}
function Records({
  page,
  user,
  notify,
  receipt,
  defaultReorder,
}: {
  page: string;
  user: Row;
  notify: Function;
  receipt: (r: Row) => void;
  defaultReorder: number;
}) {
  const [rows, setRows] = useState<Row[]>([]),
    [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [pagination, setPagination] = useState(1),
    [total, setTotal] = useState(0),
    [loading, setLoading] = useState(true),
    [modal, setModal] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [tab, setTab] = useState("Inventory"),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [payment, setPayment] = useState(""),
    [supplierOptions, setSupplierOptions] = useState<Row[]>([]),
    [history, setHistory] = useState<Row[] | null>(null);
  const path =
    page === "Inventory"
      ? tab === "Movements"
        ? "/stock/movements"
        : tab === "Receipts"
          ? "/stock/receipts"
          : "/batches?expiry=" + status
      : page === "Audit log"
        ? "/audit"
        : page === "Sales"
          ? `/sales?q=${encodeURIComponent(q)}&page=${pagination}${start ? "&start=" + start : ""}${end ? "&end=" + end : ""}${payment ? "&payment_method=" + encodeURIComponent(payment) : ""}`
          : page === "Products"
            ? `/products?q=${encodeURIComponent(q)}&status=${status}&page=${pagination}`
            : "/" +
              page.toLowerCase() +
              (page === "Customers" ? "?q=" + encodeURIComponent(q) : "");
  const reload = useCallback(() => {
    setLoading(true);
    api(path)
      .then((d) => {
        setRows(d.items || d);
        setTotal(d.total ?? d.length);
      })
      .catch((e) => notify(e.message, true))
      .finally(() => setLoading(false));
  }, [path, notify]);
  useEffect(() => {
    const t = setTimeout(reload, 200);
    return () => clearTimeout(t);
  }, [reload]);
  useEffect(() => {
    if (page === "Products" && user.role === "admin")
      api("/suppliers")
        .then(setSupplierOptions)
        .catch((e) => notify(e.message, true));
  }, [page, user.role, notify]);
  const canAdd =
    (user.role === "admin" &&
      ["Products", "Suppliers", "Users"].includes(page)) ||
    (page === "Customers" && user.role !== "cashier");
  async function submit(data: Row) {
    setBusy(true);
    try {
      const body = { ...data };
      if (page === "Users" && modal?.id) {
        delete body.username;
        if (!body.password) delete body.password;
      }
      if (page === "Products") {
        body.barcode = body.barcode || null;
        body.supplier_id = body.supplier_id ? Number(body.supplier_id) : null;
      }
      await api(
        "/" + page.toLowerCase() + (modal?.id ? "/" + modal.id : ""),
        modal?.id ? "PUT" : "POST",
        body,
      );
      setModal(null);
      notify("Record saved successfully.");
      reload();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const fields =
    page === "Products"
      ? [
          ...productFields,
          {
            key: "supplier_id",
            label: "Preferred supplier",
            options: supplierOptions.map((s) => ({
              value: String(s.id),
              label: s.name,
            })),
          },
        ]
      : page === "Suppliers"
        ? supplierFields
        : page === "Customers"
          ? customerFields
          : [
              ...(!modal?.id
                ? [{ key: "username", label: "Username", required: true }]
                : []),
              { key: "email", label: "Email", type: "email", required: true },
              {
                key: "password",
                label: modal?.id
                  ? "New password (optional, 12+ characters)"
                  : "Password (12+ characters)",
                type: "password",
                required: !modal?.id,
              },
              {
                key: "role",
                label: "Role",
                required: true,
                options: ["admin", "pharmacist", "cashier"].map((r) => ({
                  value: r,
                  label: r,
                })),
              },
            ];
  return (
    <>
      <section className="panel">
        <div className="toolbar">
          {["Products", "Customers", "Sales"].includes(page) && (
            <div className="search-field">
              <Search size={17} />
              <input
                aria-label="Search records"
                placeholder={
                  page === "Sales"
                    ? "Search receipt number…"
                    : "Search catalogue…"
                }
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPagination(1);
                }}
              />
            </div>
          )}
          {page === "Products" && (
            <select
              aria-label="Stock status"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPagination(1);
              }}
            >
              <option value="">All stock levels</option>
              <option value="low">Low stock</option>
              <option value="out">Out of stock</option>
            </select>
          )}
          {page === "Inventory" && (
            <>
              <div className="tabs">
                {["Inventory", "Movements", "Receipts"].map((t) => (
                  <button
                    className={t === tab ? "selected" : ""}
                    key={t}
                    onClick={() => setTab(t)}
                  >
                    {t === "Inventory" ? "Batches & expiry" : t}
                  </button>
                ))}
              </div>
              {tab === "Inventory" && (
                <select
                  aria-label="Expiry filter"
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                >
                  <option value="">All batches</option>
                  <option value="expired">Expired</option>
                  <option value="30">Expires in 30 days</option>
                  <option value="60">Expires in 60 days</option>
                  <option value="90">Expires in 90 days</option>
                </select>
              )}
            </>
          )}
          {page === "Sales" && (
            <>
              <input
                type="date"
                aria-label="Sales from date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
              <input
                type="date"
                aria-label="Sales to date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
              <select
                aria-label="Payment filter"
                value={payment}
                onChange={(e) => setPayment(e.target.value)}
              >
                <option value="">All payments</option>
                {["Cash", "Mobile Money", "Card", "Other"].map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            </>
          )}
          {canAdd && (
            <button
              className="primary push-right"
              onClick={() =>
                setModal(
                  page === "Products"
                    ? {
                        category: "Medicines",
                        pack_size: "1 unit",
                        reorder_level: defaultReorder,
                        selling_price: 0,
                      }
                    : {},
                )
              }
            >
              <Plus size={18} />
              Add{" "}
              {page === "Products"
                ? "product"
                : page === "Suppliers"
                  ? "supplier"
                  : page === "Customers"
                    ? "customer"
                    : "user"}
            </button>
          )}
          <button className="secondary" onClick={reload}>
            Refresh
          </button>
        </div>
        {loading ? (
          <div className="loading">Loading records…</div>
        ) : (
          <Table
            rows={rows}
            cols={columns[page === "Inventory" ? tab : page]}
            onRow={
              page === "Sales"
                ? (r) =>
                    api("/sales/" + r.id)
                      .then(receipt)
                      .catch((e) => notify(e.message, true))
                : ["Products", "Suppliers"].includes(page) &&
                    user.role === "admin"
                  ? setModal
                  : page === "Customers"
                    ? (r) =>
                        api("/customers/" + r.id + "/sales")
                          .then(setHistory)
                          .catch((e) => notify(e.message, true))
                    : undefined
            }
            action={
              ["Products", "Suppliers"].includes(page) && user.role === "admin"
                ? (r) => (
                    <button className="link" onClick={() => setModal(r)}>
                      Edit
                    </button>
                  )
                : page === "Customers"
                  ? (r) => (
                      <button className="link" onClick={() => setModal(r)}>
                        Edit
                      </button>
                    )
                  : page === "Users"
                    ? (r) => (
                        <>
                          <button className="link" onClick={() => setModal(r)}>
                            Edit
                          </button>
                          <button
                            disabled={r.id === user.id}
                            className="link"
                            onClick={async () => {
                              if (
                                !confirm(
                                  (r.active ? "Disable" : "Enable") +
                                    " this user?",
                                )
                              )
                                return;
                              try {
                                await api(
                                  "/users/" + r.id + "/active",
                                  "PATCH",
                                );
                                reload();
                                notify("User access updated.");
                              } catch (e) {
                                notify((e as Error).message, true);
                              }
                            }}
                          >
                            {r.active ? "Disable" : "Enable"}
                          </button>
                        </>
                      )
                    : undefined
            }
          />
        )}
        <div className="pagination">
          <span>
            {total} records{" "}
            {page === "Inventory"
              ? "(display limit 2,000 batches / 1,000 movements)"
              : ""}
          </span>
          {["Products", "Sales"].includes(page) && (
            <div>
              <button
                className="secondary"
                disabled={pagination === 1}
                onClick={() => setPagination(pagination - 1)}
              >
                Previous
              </button>
              <span>Page {pagination}</span>
              <button
                className="secondary"
                disabled={pagination * 50 >= total}
                onClick={() => setPagination(pagination + 1)}
              >
                Next
              </button>
            </div>
          )}
        </div>
      </section>
      {modal && (
        <Modal
          title={(modal.id ? "Edit " : "Add ") + page.toLowerCase()}
          close={() => setModal(null)}
        >
          <Form fields={fields} initial={modal} submit={submit} busy={busy} />
        </Modal>
      )}
      {history && (
        <Modal title="Customer purchase history" close={() => setHistory(null)}>
          <Table
            rows={history}
            cols={columns.Sales}
            onRow={(r) =>
              api("/sales/" + r.id)
                .then(receipt)
                .catch((e) => notify(e.message, true))
            }
          />
        </Modal>
      )}
    </>
  );
}
function Receive({ notify }: { notify: Function }) {
  const [products, setProducts] = useState<Row[]>([]),
    [suppliers, setSuppliers] = useState<Row[]>([]),
    [items, setItems] = useState<Row[]>([
      {
        product_id: "",
        batch_number: "",
        quantity: 1,
        purchase_price: 0,
        expiry_date: "",
      },
    ]),
    [supplier, setSupplier] = useState(""),
    [reference, setReference] = useState(""),
    [notes, setNotes] = useState(""),
    [busy, setBusy] = useState(false),
    [q, setQ] = useState("");
  useEffect(() => {
    api("/suppliers")
      .then(setSuppliers)
      .catch((e) => notify(e.message, true));
  }, [notify]);
  useEffect(() => {
    let live = true;
    api("/products?limit=200&q=" + encodeURIComponent(q))
      .then((d) => {
        if (live)
          setProducts((old) => {
            const map = new Map(old.map((p) => [p.id, p]));
            d.items.forEach((p: Row) => map.set(p.id, p));
            return [...map.values()];
          });
      })
      .catch((e) => notify(e.message, true));
    return () => {
      live = false;
    };
  }, [q, notify]);
  function change(i: number, k: string, v: any) {
    setItems(items.map((r, n) => (n === i ? { ...r, [k]: v } : r)));
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/stock/receive", "POST", {
        supplier_id: Number(supplier),
        reference,
        notes,
        items: items.map((i) => ({
          ...i,
          product_id: Number(i.product_id),
          quantity: Number(i.quantity),
          purchase_price: Number(i.purchase_price),
          selling_price:
            i.selling_price === "" || i.selling_price === undefined
              ? null
              : Number(i.selling_price),
          manufacturing_date: i.manufacturing_date || null,
        })),
      });
      notify("Delivery recorded and inventory increased.");
      setItems([
        {
          product_id: "",
          batch_number: "",
          quantity: 1,
          purchase_price: 0,
          expiry_date: "",
        },
      ]);
      setReference("");
      setNotes("");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel padded">
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>
            Supplier
            <select
              value={supplier}
              required
              onChange={(e) => setSupplier(e.target.value)}
            >
              <option value="">Select supplier</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Supplier invoice/reference
            <input
              value={reference}
              required
              onChange={(e) => setReference(e.target.value)}
            />
          </label>
        </div>
        <div className="section-title">
          <h2>Delivery items</h2>
          <button
            type="button"
            className="secondary"
            onClick={() =>
              setItems([
                ...items,
                {
                  product_id: "",
                  batch_number: "",
                  quantity: 1,
                  purchase_price: 0,
                  expiry_date: "",
                },
              ])
            }
          >
            <Plus size={16} />
            Add line
          </button>
        </div>
        <label className="search-field">
          <Search size={18} />
          <input
            value={q}
            placeholder="Search for additional products…"
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        {items.map((i, n) => (
          <div className="stock-line" key={n}>
            <label>
              Product
              <select
                required
                value={i.product_id}
                onChange={(e) => change(n, "product_id", e.target.value)}
              >
                <option value="">Select product</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.strength} ({p.code})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Batch number
              <input
                required
                value={i.batch_number}
                onChange={(e) => change(n, "batch_number", e.target.value)}
              />
            </label>
            <label>
              Quantity
              <input
                type="number"
                min="1"
                required
                value={i.quantity}
                onChange={(e) => change(n, "quantity", e.target.value)}
              />
            </label>
            <label>
              Unit cost (GHS)
              <input
                type="number"
                min="0"
                step=".01"
                required
                value={i.purchase_price}
                onChange={(e) => change(n, "purchase_price", e.target.value)}
              />
            </label>
            <label>
              New sale price (optional)
              <input
                type="number"
                min="0"
                step=".01"
                value={i.selling_price ?? ""}
                onChange={(e) => change(n, "selling_price", e.target.value)}
              />
            </label>
            <label>
              Manufactured (optional)
              <input
                type="date"
                value={i.manufacturing_date ?? ""}
                onChange={(e) =>
                  change(n, "manufacturing_date", e.target.value)
                }
              />
            </label>
            <label>
              Expiry date
              <input
                type="date"
                required
                value={i.expiry_date}
                min={new Date(Date.now() + 86400000).toISOString().slice(0, 10)}
                onChange={(e) => change(n, "expiry_date", e.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={items.length === 1}
              className="icon danger"
              aria-label="Remove delivery line"
              onClick={() => setItems(items.filter((_, j) => j !== n))}
            >
              <Trash2 size={18} />
            </button>
          </div>
        ))}
        <label>
          Notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <div className="form-actions">
          <span className="secure-note">
            <ShieldCheck size={17} />
            Every line creates an inventory movement.
          </span>
          <button disabled={busy} className="primary">
            {busy ? "Receiving…" : "Confirm stock received"}
          </button>
        </div>
      </form>
    </section>
  );
}
function Adjust({ notify }: { notify: Function }) {
  const [batches, setBatches] = useState<Row[]>([]),
    [busy, setBusy] = useState(false);
  const load = useCallback(
    () =>
      api("/batches")
        .then(setBatches)
        .catch((e) => notify(e.message, true)),
    [notify],
  );
  useEffect(() => {
    load();
  }, [load]);
  async function submit(v: Row) {
    if (!confirm("Apply this stock adjustment? It will be logged permanently."))
      return;
    setBusy(true);
    try {
      await api("/stock/adjust", "POST", {
        ...v,
        batch_id: Number(v.batch_id),
      });
      notify("Stock adjustment recorded.");
      load();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel padded narrow">
      <div className="notice">
        <AlertTriangle size={20} />
        <span>
          Use a negative quantity to remove damaged, expired, or missing stock.
          Use a positive quantity to correct a count. All changes require a
          reason.
        </span>
      </div>
      <Form
        fields={[
          {
            key: "batch_id",
            label: "Product / batch",
            required: true,
            options: batches.map((b) => ({
              value: String(b.id),
              label: `${b.product_name} · ${b.number} · ${b.quantity} units · expiry ${b.expiry_date}`,
            })),
          },
          {
            key: "quantity",
            label: "Quantity change (+ or −)",
            type: "number",
            required: true,
            step: "1",
          },
          {
            key: "reason",
            label: "Reason (at least 5 characters)",
            required: true,
            type: "textarea",
          },
        ]}
        busy={busy}
        submit={submit}
        label="Record adjustment"
      />
    </section>
  );
}
function Reports({ notify }: { notify: Function }) {
  const [data, setData] = useState<Row | null>(null),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [kind, setKind] = useState("sales");
  const params = `${start ? "start=" + start + "&" : ""}${end ? "end=" + end : ""}`;
  useEffect(() => {
    let live = true;
    api("/reports?" + params)
      .then((d) => {
        if (live) setData(d);
      })
      .catch((e) => notify(e.message, true));
    return () => {
      live = false;
    };
  }, [params, notify]);
  return (
    <div className="report-print">
      <section className="panel toolbar no-print">
        <label>
          From
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
        <select
          aria-label="Export report"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          {["sales", "inventory", "movements", "expiry"].map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <button
          className="secondary"
          onClick={() =>
            download(
              "/reports/export?kind=" + kind + "&" + params,
              "pharmastock-" + kind + ".csv",
            ).catch((e) => notify(e.message, true))
          }
        >
          <Download size={17} />
          Export CSV
        </button>
        <button className="secondary" onClick={() => window.print()}>
          <Printer size={17} />
          Print / save PDF
        </button>
      </section>
      {!data ? (
        <div className="loading">Calculating reports…</div>
      ) : (
        <>
          <div className="stats">
            {[
              ["Gross sales", data.gross_sales],
              ["Gross profit estimate", data.gross_profit],
              ["Sellable stock value", data.stock_valuation],
              ["Refunded sales", data.refunds],
            ].map(([k, v]) => (
              <section className="stat" key={k}>
                <span>{k}</span>
                <strong>{fmt(v)}</strong>
                <small>Recorded costs and selected sale dates</small>
              </section>
            ))}
          </div>
          <section className="panel padded">
            <h2>Financial summary</h2>
            <div className="metrics-line">
              <span>{data.transactions} completed transactions</span>
              <span>Net sales: {fmt(data.net_sales)}</span>
              <span>Discounts: {fmt(data.discounts)}</span>
              <span>Tax: {fmt(data.tax)}</span>
              <span>Cost of goods: {fmt(data.cost_of_goods)}</span>
            </div>
            <p className="muted-text">
              Gross profit excludes operating expenses. Refund totals refer to
              refunded sales in the selected sale-date period. Stock valuation
              is current, regardless of sale-date filters.
            </p>
          </section>
          {["day", "week", "month", "payment", "staff", "category"].map((d) => (
            <section className="panel" key={d}>
              <div className="panel-heading">
                <h2>Sales by {d}</h2>
              </div>
              <Table
                rows={data.groups.filter((g: Row) => g.dimension === d)}
                cols={[
                  ["name", d],
                  ["sales", "Sales"],
                ]}
              />
            </section>
          ))}
          <section className="panel">
            <div className="panel-heading">
              <h2>Product performance</h2>
            </div>
            <Table
              rows={data.products}
              cols={[
                ["name", "Product"],
                ["quantity", "Units sold"],
                ["sales", "Sales before discount and tax"],
              ]}
            />
          </section>
          <section className="panel padded">
            <h2>No sales in this period</h2>
            <p className="muted-text">
              {data.slow_moving.join(", ") || "Every active product has sales."}
            </p>
          </section>
        </>
      )}
    </div>
  );
}
function SettingsPage({
  config,
  onChange,
  notify,
}: {
  config: Row;
  onChange: (r: Row) => void;
  notify: Function;
}) {
  const [busy, setBusy] = useState(false);
  async function save(v: Row) {
    setBusy(true);
    try {
      const result = await api("/settings", "PUT", {
        ...v,
        payment_methods:
          typeof v.payment_methods === "string"
            ? v.payment_methods
                .split(",")
                .map((s: string) => s.trim())
                .filter(Boolean)
            : v.payment_methods,
      });
      onChange(result);
      notify("Pharmacy settings updated.");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel padded">
      <Form
        initial={{
          ...config,
          payment_methods: config.payment_methods.join(", "),
        }}
        busy={busy}
        submit={save}
        fields={[
          { key: "pharmacy_name", label: "Pharmacy name", required: true },
          { key: "address", label: "Address" },
          { key: "phone", label: "Telephone" },
          { key: "email", label: "Email", type: "email" },
          { key: "logo_url", label: "Logo URL (HTTPS)", type: "url" },
          { key: "currency", label: "Currency code", required: true },
          {
            key: "tax_percent",
            label: "Tax (%)",
            type: "number",
            min: 0,
            step: ".01",
            required: true,
          },
          {
            key: "expiry_warning_days",
            label: "Expiry alert window (days)",
            type: "number",
            min: 1,
            required: true,
          },
          {
            key: "default_reorder_level",
            label: "Default reorder level",
            type: "number",
            min: 0,
            required: true,
          },
          {
            key: "payment_methods",
            label: "Payment methods, comma separated",
            required: true,
          },
          { key: "receipt_footer", label: "Receipt footer", type: "textarea" },
        ]}
      />
    </section>
  );
}
function Receipt({
  sale,
  close,
  notify,
  admin,
}: {
  sale: Row;
  close: () => void;
  notify: Function;
  admin: boolean;
}) {
  const [current, setCurrent] = useState(sale),
    [refund, setRefund] = useState(false),
    [busy, setBusy] = useState(false);
  const receiptRef = useRef<HTMLDivElement>(null);
  const config = current.pharmacy_snapshot;
  async function reverse(v: Row) {
    setBusy(true);
    try {
      const result = await api("/sales/" + current.id + "/refund", "POST", v);
      setCurrent(result);
      setRefund(false);
      notify("Refund recorded.");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  function exportReceipt() {
    const html =
      '<!doctype html><html><head><meta charset="utf-8"><title>PharmaStock Receipt</title><style>body{font:12px monospace;max-width:80mm;margin:20px auto}table{width:100%;font-size:11px}h2,p{text-align:center}.receipt-totals div{display:flex;justify-content:space-between}.receipt-header{text-align:center}img{max-height:50px}</style></head><body>' +
      receiptRef.current?.outerHTML +
      "</body></html>";
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = current.receipt_number + ".html";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <Modal title="Sale receipt" close={close}>
      <div className="receipt-sheet" ref={receiptRef}>
        <div className="receipt-header">
          {config.logo_url && <img src={config.logo_url} alt="Pharmacy logo" />}
          <h2>{config.pharmacy_name}</h2>
          <p>
            {config.address}
            <br />
            {config.phone}
          </p>
          <b>{current.status === "refunded" ? "REFUNDED" : "SALE RECEIPT"}</b>
          <p>
            {current.receipt_number}
            <br />
            {dateText(current.created_at)}
            <br />
            Staff: {current.cashier}
          </p>
        </div>
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {current.items.map((i: Row) => (
              <tr key={i.id}>
                <td>{i.product_name}</td>
                <td>{i.quantity}</td>
                <td>{i.unit_price.toFixed(2)}</td>
                <td>{i.total.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="receipt-totals">
          {[
            ["Subtotal", "subtotal"],
            ["Discount", "discount"],
            ["Tax", "tax"],
            ["Grand total", "total"],
            ["Amount paid", "amount_paid"],
            ["Change", "change"],
          ].map(([l, k]) => (
            <div key={k}>
              <span>{l}</span>
              <b>{fmt(current[k], config.currency)}</b>
            </div>
          ))}
        </div>
        <p>
          Payment: {current.payment_method}
          <br />
          {config.receipt_footer}
        </p>
        {current.return && (
          <p>
            Refund reason: {current.return.reason}
            <br />
            Stock returned: {current.return.restock ? "Yes" : "No"}
          </p>
        )}
      </div>
      <div className="receipt-actions no-print">
        <button className="primary" onClick={() => window.print()}>
          <Printer size={17} />
          Print / PDF
        </button>
        <button className="secondary" onClick={exportReceipt}>
          <Download size={17} />
          Download
        </button>
        <button className="secondary" onClick={close}>
          Close receipt
        </button>
        {admin && current.status === "completed" && (
          <button className="link danger" onClick={() => setRefund(!refund)}>
            Refund sale
          </button>
        )}
      </div>
      {refund && (
        <div className="no-print">
          <div className="notice">
            Full-sale refund only. Confirm the actual refund outside this
            system. Restock only products accepted under your pharmacy's return
            policy.
          </div>
          <Form
            busy={busy}
            submit={reverse}
            fields={[
              {
                key: "reason",
                label: "Refund reason",
                type: "textarea",
                required: true,
              },
              {
                key: "restock",
                label: "Eligible, unopened stock approved for restocking",
                type: "checkbox",
              },
            ]}
            label="Confirm full refund"
          />
        </div>
      )}
    </Modal>
  );
}
