import { useMemo, useState } from "react";

type Page =
  | "Overview"
  | "Transactions"
  | "Savings"
  | "Investments"
  | "Financial Goals"
  | "Insights"
  | "Settings";

const navItems: { label: Page; icon: string }[] = [
  { label: "Overview", icon: "grid" },
  { label: "Transactions", icon: "card" },
  { label: "Savings", icon: "vault" },
  { label: "Investments", icon: "trend" },
  { label: "Financial Goals", icon: "target" },
  { label: "Insights", icon: "chart" },
  { label: "Settings", icon: "settings" },
];

const transactions = [
  { merchant: "Northstar Studio", category: "Income", date: "May 28", amount: 4200, mark: "NS" },
  { merchant: "Whole Foods Market", category: "Groceries", date: "May 27", amount: -86.42, mark: "WF" },
  { merchant: "Adobe", category: "Subscriptions", date: "May 26", amount: -22.99, mark: "AD" },
  { merchant: "The Green Table", category: "Dining", date: "May 25", amount: -48.2, mark: "GT" },
  { merchant: "City Electric", category: "Utilities", date: "May 24", amount: -74.18, mark: "CE" },
  { merchant: "Metro Transit", category: "Transport", date: "May 23", amount: -24, mark: "MT" },
  { merchant: "Acme Internet", category: "Utilities", date: "May 21", amount: -59, mark: "AI" },
];

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></>,
    card: <><rect x="3" y="5" width="18" height="14" rx="3" /><path d="M3 10h18" /></>,
    vault: <><path d="M4 7h16v12H4z" /><path d="M2 7h20M8 11v4m4-4v4m4-4v4M3 19h18" /></>,
    trend: <><path d="m4 17 5-5 4 3 7-8" /><path d="M15 7h5v5" /></>,
    target: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M18 6 21 3" /></>,
    chart: <><path d="M4 20V10m6 10V4m6 16v-7m5 7H2" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    arrow: <><path d="M5 12h14" /><path d="m14 7 5 5-5 5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    shield: <><path d="M12 3 4 6v5c0 5 3.4 8.4 8 10 4.6-1.6 8-5 8-10V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></>,
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    x: <path d="m6 6 12 12M18 6 6 18" />,
  };
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function Button({ children, variant = "primary", onClick, disabled = false }: { children: React.ReactNode; variant?: "primary" | "secondary" | "ghost"; onClick?: () => void; disabled?: boolean }) {
  return <button className={`button ${variant}`} onClick={onClick} disabled={disabled}>{children}</button>;
}

function PageHeading({ title, subtitle, action }: { title: string; subtitle: string; action?: React.ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">FINOVATE</div><div className="page-title">{title}</div><div className="page-subtitle">{subtitle}</div></div>{action}</div>;
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warning" }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

function Money({ children, small = false }: { children: React.ReactNode; small?: boolean }) {
  return <div className={small ? "money small" : "money"}>{children}</div>;
}

function Sidebar({ active, setActive }: { active: Page; setActive: (page: Page) => void }) {
  return <aside className="sidebar">
    <div className="brand"><div className="brand-mark">F</div><span>finovate</span></div>
    <nav className="side-nav" aria-label="Main navigation">
      {navItems.map((item) => <button key={item.label} className={active === item.label ? "nav-item active" : "nav-item"} onClick={() => setActive(item.label)}><Icon name={item.icon} /><span>{item.label}</span></button>)}
    </nav>
    <div className="sidebar-bottom">
      <div className="connection"><span className="status-dot" /><div><strong>Accounts connected</strong><span>Synced 4 min ago</span></div></div>
      <button className="profile"><span className="avatar">AM</span><span><strong>Alex Morgan</strong><small>alex@example.com</small></span><Icon name="chevron" size={16} /></button>
    </div>
  </aside>;
}

function LineChart() {
  return <div className="chart-wrap">
    <div className="chart-y"><span>$25k</span><span>$20k</span><span>$15k</span><span>$10k</span></div>
    <svg className="line-chart" viewBox="0 0 800 260" preserveAspectRatio="none" role="img" aria-label="Cash balance grew from $15,200 to $21,840 over six months">
      <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2f7d62" stopOpacity=".18" /><stop offset="100%" stopColor="#2f7d62" stopOpacity="0" /></linearGradient></defs>
      <path className="gridline" d="M0 30H800M0 95H800M0 160H800M0 225H800" />
      <path className="area" d="M0 205 C80 194 100 180 160 184 S265 140 330 153 S430 122 490 130 S585 91 650 104 S725 61 800 55 V260 H0Z" />
      <path className="previous" d="M0 218 C120 195 160 202 240 180 S380 177 460 143 S600 150 800 110" />
      <path className="current" d="M0 205 C80 194 100 180 160 184 S265 140 330 153 S430 122 490 130 S585 91 650 104 S725 61 800 55" />
      <circle cx="800" cy="55" r="6" className="chart-point" />
    </svg>
    <div className="chart-x"><span>Dec</span><span>Jan</span><span>Feb</span><span>Mar</span><span>Apr</span><span>May</span></div>
  </div>;
}

function SummaryCard({ label, value, detail, tone }: { label: string; value: string; detail: string; tone?: "good" | "warning" }) {
  return <Card className="summary-card"><div className="label">{label}</div><Money>{value}</Money><div className={`summary-detail ${tone || ""}`}>{tone === "good" && <Icon name="trend" size={15} />}{detail}</div></Card>;
}

function TransactionsList({ limit }: { limit?: number }) {
  return <div className="transaction-list">{transactions.slice(0, limit).map((item) =>
    <button className="transaction-row" key={item.merchant}>
      <span className="merchant-mark">{item.mark}</span>
      <span className="transaction-name"><strong>{item.merchant}</strong><small>{item.date} ┬╖ {item.category}</small></span>
      <span className={item.amount > 0 ? "amount positive" : "amount"}>{item.amount > 0 ? "+" : "ΓêÆ"}${Math.abs(item.amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
      <Icon name="chevron" size={16} />
    </button>)}</div>;
}

function Overview({ onReview }: { onReview: () => void }) {
  const [range, setRange] = useState("6M");
  return <>
    <div className="overview-heading"><div><div className="page-title">Good afternoon, Alex.</div><div className="page-subtitle">Wednesday, May 29 ┬╖ HereΓÇÖs how your money is doing.</div></div><Pill tone="good"><span className="status-dot" /> All accounts synced</Pill></div>
    <div className="summary-grid">
      <SummaryCard label="Total cash" value="$21,840" detail="+$1,240 this month" tone="good" />
      <SummaryCard label="Monthly income" value="$6,240" detail="92% of expected" />
      <SummaryCard label="Monthly spending" value="$3,816" detail="$184 under budget" tone="good" />
      <SummaryCard label="Potential savings" value="$1,224" detail="Estimated after reserves" />
    </div>
    <div className="dashboard-grid">
      <Card className="balance-card">
        <div className="card-header"><div><div className="section-title">Cash & savings</div><div className="card-metric">$21,840 <span>+7.2%</span></div></div><div className="range-tabs">{["1W", "1M", "3M", "6M", "1Y"].map((r) => <button className={range === r ? "active" : ""} onClick={() => setRange(r)} key={r}>{r}</button>)}</div></div>
        <div className="legend"><span><i className="legend-line current-line" />Current period</span><span><i className="legend-line previous-line" />Previous period</span></div>
        <LineChart />
      </Card>
      <Card className="opportunity-card">
        <div className="opportunity-icon"><Icon name="trend" /></div>
        <div className="eyebrow">SAVINGS OPPORTUNITY</div>
        <div className="opportunity-title">Your money could be working harder.</div>
        <div className="opportunity-copy">Based on your recent spending, upcoming bills, and preferred reserve.</div>
        <div className="breakdown"><div><span>Unallocated cash</span><strong>$4,124</strong></div><div><span>Upcoming bills</span><strong>ΓêÆ$1,400</strong></div><div><span>Minimum reserve</span><strong>ΓêÆ$1,500</strong></div><div className="total"><span>Available to consider</span><strong>$1,224</strong></div></div>
        <Button onClick={onReview}>Review savings plan <Icon name="arrow" size={17} /></Button>
        <small className="estimate-note">Estimate only. No funds will move without your approval.</small>
      </Card>
      <Card className="recent-card">
        <div className="card-header"><div><div className="section-title">Recent transactions</div><div className="muted">Your latest account activity</div></div><button className="text-link">View all <Icon name="arrow" size={15} /></button></div>
        <TransactionsList limit={5} />
      </Card>
      <Card className="insights-card">
        <div className="card-header"><div><div className="section-title">TodayΓÇÖs insights</div><div className="muted">Patterns worth knowing</div></div></div>
        <div className="insight"><span className="insight-icon down"><Icon name="trend" size={18} /></span><div><strong>Dining is down 12%</strong><span>YouΓÇÖve spent $42 less than this time last month.</span></div></div>
        <div className="insight"><span className="insight-icon"><Icon name="card" size={18} /></span><div><strong>$48 in subscriptions</strong><span>Four recurring services are due this month.</span></div></div>
        <div className="insight"><span className="insight-icon"><Icon name="target" size={18} /></span><div><strong>$150 to your goal</strong><span>Your emergency fund is almost fully funded.</span></div></div>
      </Card>
    </div>
  </>;
}

function TransactionsPage() {
  const [query, setQuery] = useState("");
  const filtered = transactions.filter((t) => t.merchant.toLowerCase().includes(query.toLowerCase()));
  return <>
    <PageHeading title="Transactions" subtitle="Review, categorize, and understand every transaction." action={<Button variant="secondary">Export CSV</Button>} />
    <div className="summary-grid compact">
      <SummaryCard label="Spent this month" value="$3,816" detail="4.6% lower than April" tone="good" />
      <SummaryCard label="Income this month" value="$6,240" detail="2 deposits" />
      <SummaryCard label="Recurring expenses" value="$642" detail="12 active payments" />
    </div>
    <Card>
      <div className="filter-row"><label className="search-box"><Icon name="search" size={18} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search merchants or categories" aria-label="Search transactions" /></label><select aria-label="Filter date"><option>May 2025</option></select><select aria-label="Filter category"><option>All categories</option></select><Button variant="secondary">Filters</Button></div>
      <div className="table-head"><span>Merchant</span><span>Category</span><span>Date</span><span>Amount</span><span /></div>
      <div className="transaction-list full">{filtered.map((item) => <button className="transaction-row" key={item.merchant}><span className="merchant-mark">{item.mark}</span><span className="transaction-name"><strong>{item.merchant}</strong><small>Checking ┬╖┬╖4821</small></span><Pill>{item.category}</Pill><span className="date-cell">{item.date}, 2025</span><span className={item.amount > 0 ? "amount positive" : "amount"}>{item.amount > 0 ? "+" : "ΓêÆ"}${Math.abs(item.amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}</span><Icon name="chevron" size={16} /></button>)}</div>
    </Card>
  </>;
}

function SavingsPage({ onReview }: { onReview: () => void }) {
  const [emergency, setEmergency] = useState(60);
  return <>
    <PageHeading title="Savings Center" subtitle="Build a plan around whatΓÇÖs truly safe to save." action={<Button onClick={onReview}>Review savings plan</Button>} />
    <div className="savings-hero">
      <Card className="savings-total"><div className="label">CURRENT SAVINGS</div><Money>$9,850</Money><div className="progress-label"><span>Emergency fund</span><strong>98.5%</strong></div><div className="progress"><i style={{ width: "98.5%" }} /></div><div className="muted">$150 remaining toward your $10,000 target</div></Card>
      <Card className="surplus-card"><div><div className="label">POTENTIAL SURPLUS</div><Money>$1,224</Money><div className="muted">Estimated, not yet saved</div></div><div className="surplus-ring"><strong>19.6%</strong><span>savings rate</span></div></Card>
    </div>
    <div className="two-column">
      <Card><div className="section-title">How we calculated your surplus</div><div className="waterfall"><div><span>Cash available after income</span><strong>$6,240</strong></div><div><span>Monthly spending</span><strong>ΓêÆ$3,816</strong></div><div><span>Upcoming bills</span><strong>ΓêÆ$1,200</strong></div><div className="total"><span>Potential surplus</span><strong>$1,224</strong></div></div><div className="callout"><Icon name="shield" /><span>Your $1,500 minimum cash reserve is protected in this estimate.</span></div></Card>
      <Card><div className="section-title">Proposed allocation</div><div className="allocation-bar"><i style={{ width: `${emergency}%` }} /><i /><i /></div><div className="allocation-list"><label><span><i className="dot green" />Emergency savings</span><strong>${Math.round(1224 * emergency / 100)}</strong></label><input type="range" min="30" max="80" value={emergency} onChange={(e) => setEmergency(Number(e.target.value))} aria-label="Emergency savings allocation" /><label><span><i className="dot gold" />Short-term goals</span><strong>${Math.round(1224 * (90 - emergency) / 100)}</strong></label><label><span><i className="dot navy" />Long-term investing</span><strong>$122</strong></label></div><div className="muted">Adjusting this preview does not move money.</div></Card>
    </div>
    <div className="section-heading"><div><div className="section-title">Savings opportunities</div><div className="muted">Personalized ideas based on sample activity</div></div></div>
    <div className="recommendation-grid">
      {[["Subscriptions", "Review 2 rarely used services", "$28/mo", "Four services total $48. Two have not been used recently."], ["Weekly target", "Set aside $75 each Friday", "$300/mo", "Your lowest weekly balance would remain above your reserve."], ["Dining", "Keep this monthΓÇÖs momentum", "$42/mo", "Dining is already 12% lower than your April pace."]].map(([tag, title, value, copy]) => <Card key={title} className="recommendation"><Pill tone="good">{tag}</Pill><div className="recommend-title">{title}</div><Money small>{value}</Money><p>{copy}</p><button className="text-link">Explore idea <Icon name="arrow" size={15} /></button></Card>)}
    </div>
  </>;
}

const etfs = [
  { ticker: "VTI", name: "Vanguard Total Stock Market ETF", type: "US broad market", fee: "0.03%", risk: "Higher", return: "+11.2%" },
  { ticker: "BND", name: "Vanguard Total Bond Market ETF", type: "US bonds", fee: "0.03%", risk: "Moderate", return: "+3.1%" },
  { ticker: "SGOV", name: "iShares 0ΓÇô3 Month Treasury Bond ETF", type: "Treasury", fee: "0.09%", risk: "Lower", return: "+5.0%" },
];

function InvestmentsPage({ onReview }: { onReview: () => void }) {
  const [tab, setTab] = useState<"Portfolio" | "Explore ETFs" | "Calculator">("Portfolio");
  const [years, setYears] = useState(10);
  const projection = useMemo(() => Math.round(5000 * Math.pow(1.06, years) + 300 * ((Math.pow(1.06 / 12 + 1, years * 12) - 1) / (0.06 / 12))), [years]);
  return <>
    <PageHeading title="Investments" subtitle="Explore diversified options with the risks made clear." action={<Button onClick={onReview}>Review investment plan</Button>} />
    <div className="top-tabs">{(["Portfolio", "Explore ETFs", "Calculator"] as const).map((t) => <button key={t} onClick={() => setTab(t)} className={tab === t ? "active" : ""}>{t}</button>)}</div>
    {tab === "Portfolio" && <>
      <div className="summary-grid compact"><SummaryCard label="Portfolio value" value="$14,280" detail="+$680 all time" tone="good" /><SummaryCard label="Contributed" value="$13,600" detail="Across 18 deposits" /><SummaryCard label="Unrealized gain" value="+$680" detail="+5.0% since inception" tone="good" /></div>
      <div className="two-column"><Card><div className="section-title">Portfolio performance</div><div className="card-metric">$14,280 <span>+$384 (2.8%)</span></div><LineChart /></Card><Card><div className="section-title">Current allocation</div><div className="donut-wrap"><div className="donut"><div><strong>3</strong><span>funds</span></div></div><div className="allocation-list"><label><span><i className="dot green" />US stocks ┬╖ VTI</span><strong>60%</strong></label><label><span><i className="dot gold" />US bonds ┬╖ BND</span><strong>30%</strong></label><label><span><i className="dot navy" />Treasuries ┬╖ SGOV</span><strong>10%</strong></label></div></div></Card></div>
      <div className="disclosure"><Icon name="shield" size={18} /> Investment values can rise or fall. Past performance does not guarantee future results.</div>
    </>}
    {tab === "Explore ETFs" && <Card><div className="filter-row"><label className="search-box"><Icon name="search" size={18} /><input placeholder="Search by fund or ticker" /></label><select><option>All asset classes</option></select><select><option>All risk levels</option></select></div><div className="etf-list">{etfs.map((e) => <button className="etf-row" key={e.ticker}><span className="ticker">{e.ticker}</span><span><strong>{e.name}</strong><small>{e.type}</small></span><span><small>Expense ratio</small><strong>{e.fee}</strong></span><span><small>5Y annualized*</small><strong className="positive">{e.return}</strong></span><Pill tone={e.risk === "Lower" ? "good" : "neutral"}>{e.risk} risk</Pill><Icon name="chevron" size={16} /></button>)}</div><div className="estimate-note">*Illustrative historical sample data. Returns vary and may be negative.</div></Card>}
    {tab === "Calculator" && <div className="calculator-grid"><Card><div className="section-title">Adjust assumptions</div><label className="field-label">Time horizon <strong>{years} years</strong></label><input type="range" min="1" max="30" value={years} onChange={(e) => setYears(Number(e.target.value))} /><label className="field-label">Starting balance <input value="$5,000" readOnly /></label><label className="field-label">Monthly contribution <input value="$300" readOnly /></label><label className="field-label">Assumed annual return <input value="6.0%" readOnly /></label></Card><Card className="projection"><div className="eyebrow">HYPOTHETICAL PROJECTION</div><div className="muted">Estimated portfolio value in {years} years</div><Money>${projection.toLocaleString()}</Money><div className="projection-bars"><div><span>Invested portfolio</span><i style={{ width: "88%" }} /></div><div><span>Savings at 4.0% APY</span><i style={{ width: "70%" }} /></div></div><div className="disclosure">These outputs are estimates, not predictions. Returns and rates can change, and investments can lose value.</div></Card></div>}
  </>;
}

function GoalsPage() {
  const [showNew, setShowNew] = useState(false);
  const goals = [
    { name: "Emergency fund", icon: "shield", current: 9850, target: 10000, date: "June 2025", monthly: 150 },
    { name: "Japan trip", icon: "target", current: 3200, target: 6000, date: "April 2026", monthly: 280 },
    { name: "New computer", icon: "grid", current: 850, target: 2400, date: "November 2025", monthly: 260 },
  ];
  return <>
    <PageHeading title="Financial Goals" subtitle="Turn important plans into achievable monthly steps." action={<Button onClick={() => setShowNew(true)}><Icon name="plus" size={17} /> Create a goal</Button>} />
    <div className="goal-overview"><div><span>Total saved toward goals</span><Money>$13,900</Money></div><div><span>Monthly goal contributions</span><Money>$690</Money></div><div><span>Goals on track</span><Money>3 of 3</Money></div></div>
    <div className="goals-grid">{goals.map((g) => { const percent = Math.round(g.current / g.target * 100); return <Card className="goal-card" key={g.name}><div className="goal-icon"><Icon name={g.icon} /></div><button className="goal-menu">ΓÇóΓÇóΓÇó</button><div className="recommend-title">{g.name}</div><div className="goal-money"><strong>${g.current.toLocaleString()}</strong><span>of ${g.target.toLocaleString()}</span></div><div className="progress"><i style={{ width: `${percent}%` }} /></div><div className="progress-label"><strong>{percent}% complete</strong><span>${(g.target - g.current).toLocaleString()} remaining</span></div><div className="goal-footer"><span>Target ┬╖ {g.date}</span><strong>${g.monthly}/month</strong></div></Card> })}</div>
    {showNew && <Modal title="Create a financial goal" onClose={() => setShowNew(false)}><label className="field-label">Goal name<input placeholder="e.g. Education expenses" /></label><div className="form-grid"><label className="field-label">Target amount<input placeholder="$0" /></label><label className="field-label">Target date<input type="date" /></label></div><div className="modal-actions"><Button variant="ghost" onClick={() => setShowNew(false)}>Cancel</Button><Button onClick={() => setShowNew(false)}>Create goal</Button></div></Modal>}
  </>;
}

function InsightsPage() {
  return <>
    <PageHeading title="Insights & Analytics" subtitle="Clear patterns from your income, spending, and savings." action={<select className="period-select"><option>Last 6 months</option></select>} />
    <div className="summary-grid compact"><SummaryCard label="Average monthly income" value="$6,080" detail="+3.2% over prior period" tone="good" /><SummaryCard label="Average monthly spending" value="$3,940" detail="ΓêÆ4.1% over prior period" tone="good" /><SummaryCard label="Average savings rate" value="19.2%" detail="+2.4 percentage points" tone="good" /></div>
    <div className="two-column insights-layout"><Card><div className="section-title">Income vs. expenses</div><div className="muted">November 2024 ΓÇô May 2025</div><div className="bar-chart">{[72,68,78,74,82,76].map((h, i) => <div className="bar-group" key={i}><i className="income-bar" style={{ height: `${h}%` }} /><i className="expense-bar" style={{ height: `${h - 25}%` }} /><span>{["Dec","Jan","Feb","Mar","Apr","May"][i]}</span></div>)}</div><div className="legend"><span><i className="dot green" />Income</span><span><i className="dot gold" />Expenses</span></div></Card><Card><div className="section-title">Spending by category</div><div className="donut-wrap"><div className="donut spending"><div><strong>$3,816</strong><span>May spending</span></div></div><div className="allocation-list"><label><span><i className="dot green" />Housing</span><strong>38%</strong></label><label><span><i className="dot gold" />Food & dining</span><strong>22%</strong></label><label><span><i className="dot navy" />Transport</span><strong>14%</strong></label><label><span><i className="dot gray" />Other</span><strong>26%</strong></label></div></div></Card></div>
    <Card><div className="section-title">What changed this month</div><div className="insight-strip"><div><Pill tone="good">Positive</Pill><strong>Dining fell by $42</strong><span>Your lower dining spend is the main reason May expenses are under budget.</span></div><div><Pill tone="warning">Watch</Pill><strong>Utilities rose by 8%</strong><span>Electricity was $18 higher than your three-month average.</span></div><div><Pill>Recurring</Pill><strong>Four subscriptions</strong><span>Your next subscription renewal is Adobe for $22.99 on June 26.</span></div></div></Card>
  </>;
}

function SettingsPage() {
  const [section, setSection] = useState("Profile");
  const sections = ["Profile", "Connected accounts", "Savings preferences", "Investment preferences", "Notifications", "Security & privacy"];
  return <>
    <PageHeading title="Settings" subtitle="Manage your preferences, connections, and privacy." />
    <div className="settings-layout"><Card className="settings-nav">{sections.map((s) => <button className={section === s ? "active" : ""} onClick={() => setSection(s)} key={s}>{s}<Icon name="chevron" size={15} /></button>)}</Card><Card className="settings-panel"><div className="section-title">{section}</div><div className="muted">YouΓÇÖre always in control of your information and preferences.</div>
      {section === "Profile" ? <div className="settings-form"><div className="profile-large"><span className="avatar">AM</span><div><strong>Alex Morgan</strong><span>Personal account</span></div><Button variant="secondary">Change photo</Button></div><div className="form-grid"><label className="field-label">Full name<input value="Alex Morgan" readOnly /></label><label className="field-label">Email address<input value="alex@example.com" readOnly /></label><label className="field-label">Preferred currency<select><option>USD ΓÇö US Dollar</option></select></label><label className="field-label">Region<select><option>United States</option></select></label></div><Button>Save changes</Button></div>
      : section === "Connected accounts" ? <div className="account-list"><div className="account-row"><span className="merchant-mark">CB</span><div><strong>Chase Checking ┬╖┬╖4821</strong><span><i className="status-dot" /> Connected ┬╖ Synced 4 min ago</span></div><Button variant="secondary">Manage</Button></div><div className="account-row"><span className="merchant-mark">HY</span><div><strong>High-Yield Savings ┬╖┬╖9014</strong><span><i className="status-dot" /> Connected ┬╖ Synced 4 min ago</span></div><Button variant="secondary">Manage</Button></div><Button><Icon name="plus" size={17} /> Connect an account</Button></div>
      : <div className="preference-list">{["Enable personalized insights", "Receive important account alerts", "Use connected account data for estimates"].map((x, i) => <label className="toggle-row" key={x}><span><strong>{x}</strong><small>{i === 2 ? "Read-only transaction data is used to calculate estimates." : "You can change this at any time."}</small></span><input type="checkbox" defaultChecked={i !== 1} /></label>)}</div>}
    </Card></div>
  </>;
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><div className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}><div className="modal-header"><div className="section-title">{title}</div><button className="icon-button" onClick={onClose} aria-label="Close"><Icon name="x" /></button></div>{children}</div></div>;
}

function ReviewModal({ onClose }: { onClose: () => void }) {
  const [confirmed, setConfirmed] = useState(false);
  return <Modal title={confirmed ? "Plan ready for your review" : "Review proposed plan"} onClose={onClose}>{confirmed ? <div className="success-state"><div className="success-icon"><Icon name="check" size={28} /></div><div className="opportunity-title">Nothing has moved yet.</div><p>Your proposed allocation has been saved. You can confirm each transfer separately when connected transfers become available.</p><Button onClick={onClose}>Return to dashboard</Button></div> : <><div className="review-amount"><span>Amount to consider saving</span><Money>$1,224</Money><Pill>Estimated</Pill></div><div className="breakdown"><div><span>Emergency savings</span><strong>$734</strong></div><div><span>Short-term goals</span><strong>$368</strong></div><div><span>Long-term investing</span><strong>$122</strong></div></div><div className="callout"><Icon name="shield" /><span>This is a proposed plan only. Reviewing it will not transfer or invest funds.</span></div><div className="modal-actions"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={() => setConfirmed(true)}>Save proposed plan</Button></div></>}</Modal>;
}

export default function App() {
  const [active, setActive] = useState<Page>("Overview");
  const [reviewing, setReviewing] = useState(false);
  const [mobileMenu, setMobileMenu] = useState(false);
  const content: Record<Page, React.ReactNode> = {
    Overview: <Overview onReview={() => setReviewing(true)} />,
    Transactions: <TransactionsPage />,
    Savings: <SavingsPage onReview={() => setReviewing(true)} />,
    Investments: <InvestmentsPage onReview={() => setReviewing(true)} />,
    "Financial Goals": <GoalsPage />,
    Insights: <InsightsPage />,
    Settings: <SettingsPage />,
  };
  const go = (page: Page) => { setActive(page); setMobileMenu(false); window.scrollTo(0, 0); };
  return <div className="app-shell">
    <Sidebar active={active} setActive={go} />
    <header className="mobile-header"><div className="brand"><div className="brand-mark">F</div><span>finovate</span></div><button className="icon-button" onClick={() => setMobileMenu(!mobileMenu)} aria-label="Open menu"><Icon name="menu" /></button></header>
    {mobileMenu && <div className="mobile-menu">{navItems.map((item) => <button key={item.label} className={active === item.label ? "active" : ""} onClick={() => go(item.label)}><Icon name={item.icon} />{item.label}</button>)}</div>}
    <main className="main"><div className="desktop-topbar"><div className="breadcrumbs">{active === "Overview" ? "Your financial home" : `Home / ${active}`}</div><div className="top-actions"><button className="icon-button" aria-label="Notifications"><Icon name="bell" /><i className="notification-dot" /></button><span className="avatar small">AM</span></div></div><div className="content">{content[active]}</div></main>
    <nav className="bottom-nav">{navItems.slice(0, 4).map((item) => <button key={item.label} className={active === item.label ? "active" : ""} onClick={() => go(item.label)}><Icon name={item.icon} /><span>{item.label}</span></button>)}<button onClick={() => setMobileMenu(true)}><Icon name="menu" /><span>More</span></button></nav>
    {reviewing && <ReviewModal onClose={() => setReviewing(false)} />}
  </div>;
}
