"""
PropertyFinder Report Generator
================================
Generates a self-contained HTML dashboard from scraped JSON files.
Can be run standalone or imported by the scraper.
"""

import json
import os
from datetime import datetime
from collections import Counter


def load_json(filepath):
    """Load JSON file, return empty list if not found."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def fmt_price(val):
    """Format a number as a price string."""
    if val is None:
        return "N/A"
    try:
        return f"{int(val):,}"
    except (ValueError, TypeError):
        return str(val)


def generate_report(
    listings=None, projects=None, agencies=None,
    output_path="propertyfinder_report.html",
    data_dir="."
):
    """Generate an interactive HTML report from scraped data."""

    # Load from files if not provided
    if listings is None:
        listings = load_json(os.path.join(data_dir, "propertyfinder_selenium_listings.json"))
    if projects is None:
        projects = load_json(os.path.join(data_dir, "propertyfinder_selenium_projects.json"))
    if agencies is None:
        agencies = load_json(os.path.join(data_dir, "propertyfinder_selenium_agencies.json"))

    # --- Compute stats ---
    prices = [l["price"] for l in listings if l.get("price") and l["price"] > 0]
    avg_price = int(sum(prices) / len(prices)) if prices else 0
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0

    # Location distribution
    loc_counts = Counter()
    for l in listings:
        loc = l.get("location_name") or l.get("location_full", "Unknown")
        loc_counts[loc] += 1
    top_locations = loc_counts.most_common(10)

    # Property type distribution
    type_counts = Counter(l.get("property_type", "Unknown") for l in listings)
    top_types = type_counts.most_common(8)

    # Price buckets for histogram
    if prices:
        bucket_size = max(1, (max_price - min_price) // 8)
        buckets = {}
        for p in prices:
            key = f"{fmt_price((p // bucket_size) * bucket_size)}"
            buckets[key] = buckets.get(key, 0) + 1
        price_labels = list(buckets.keys())[:8]
        price_values = list(buckets.values())[:8]
    else:
        price_labels, price_values = [], []

    # Bedroom distribution
    bed_counts = Counter()
    for l in listings:
        b = l.get("bedrooms")
        bed_counts[str(b) if b is not None else "N/A"] += 1
    bed_items = sorted(bed_counts.items(), key=lambda x: (x[0] == "N/A", x[0]))

    # Agency stats
    total_agency_props = sum(a.get("total_properties", 0) or 0 for a in agencies)
    total_agents = sum(a.get("agent_count", 0) or 0 for a in agencies)

    now = datetime.now().strftime("%B %d, %Y at %H:%M")

    # --- Build listing rows ---
    listing_rows = ""
    for l in listings[:100]:
        listing_rows += f"""<tr>
<td>{l.get('title','')[:50]}</td>
<td>{fmt_price(l.get('price'))} {l.get('currency','EGP')}</td>
<td>{l.get('bedrooms','—')}</td><td>{l.get('bathrooms','—')}</td>
<td>{l.get('size_sqm','—')}</td>
<td>{(l.get('location_name') or l.get('location_full',''))[:30]}</td>
</tr>"""

    # --- Build project rows ---
    project_rows = ""
    for p in projects:
        delivery = p.get("delivery_date", "")
        if delivery and "T" in str(delivery):
            delivery = str(delivery).split("T")[0]
        project_rows += f"""<tr>
<td>{p.get('name','')}</td>
<td>{p.get('developer','—')}</td>
<td>{(p.get('location') or '—')[:30]}</td>
<td>{fmt_price(p.get('starting_price'))} EGP</td>
<td>{p.get('status','—').replace('_',' ').title()}</td>
<td>{delivery or '—'}</td>
<td>{p.get('property_types','—')}</td>
</tr>"""

    # --- Build agency rows ---
    agency_rows = ""
    for a in agencies:
        agency_rows += f"""<tr>
<td>{a.get('name','')}</td>
<td>{a.get('agent_count','—')}</td>
<td>{fmt_price(a.get('total_properties'))}</td>
<td>{fmt_price(a.get('listings_for_sale'))}</td>
<td>{fmt_price(a.get('listings_for_rent'))}</td>
<td>{a.get('phone','—')}</td>
</tr>"""

    # Chart data
    loc_labels_js = json.dumps([l[0][:20] for l in top_locations])
    loc_values_js = json.dumps([l[1] for l in top_locations])
    price_labels_js = json.dumps(price_labels)
    price_values_js = json.dumps(price_values)
    type_labels_js = json.dumps([t[0] for t in top_types])
    type_values_js = json.dumps([t[1] for t in top_types])
    bed_labels_js = json.dumps([b[0] for b in bed_items])
    bed_values_js = json.dumps([b[1] for b in bed_items])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PropertyFinder Egypt — Scraping Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',sans-serif;background:#0f0f1a;color:#e0e0f0;line-height:1.6}}
.container{{max-width:1400px;margin:0 auto;padding:20px}}

/* Header */
.header{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);
padding:40px;border-radius:16px;margin-bottom:30px;position:relative;overflow:hidden}}
.header::before{{content:'';position:absolute;top:-50%;right:-20%;width:400px;height:400px;
background:radial-gradient(circle,rgba(233,69,96,0.15),transparent 70%);pointer-events:none}}
.header h1{{font-size:2.2rem;font-weight:700;
background:linear-gradient(135deg,#e94560,#f5a623);-webkit-background-clip:text;
-webkit-text-fill-color:transparent;margin-bottom:8px}}
.header p{{color:#8892b0;font-size:0.95rem}}
.badge{{display:inline-block;background:rgba(233,69,96,0.15);color:#e94560;
padding:4px 12px;border-radius:20px;font-size:0.8rem;font-weight:500;margin-top:8px}}

/* Metric Cards */
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:30px}}
.metric-card{{background:linear-gradient(145deg,#1a1a2e,#16213e);border:1px solid rgba(255,255,255,0.06);
border-radius:12px;padding:24px;text-align:center;transition:transform 0.2s,box-shadow 0.2s}}
.metric-card:hover{{transform:translateY(-4px);box-shadow:0 8px 30px rgba(233,69,96,0.1)}}
.metric-card .value{{font-size:2rem;font-weight:700;
background:linear-gradient(135deg,#e94560,#f5a623);-webkit-background-clip:text;
-webkit-text-fill-color:transparent}}
.metric-card .label{{color:#8892b0;font-size:0.85rem;margin-top:4px}}

/* Section */
.section{{background:linear-gradient(145deg,#1a1a2e,#16213e);border:1px solid rgba(255,255,255,0.06);
border-radius:12px;padding:24px;margin-bottom:24px}}
.section h2{{font-size:1.3rem;font-weight:600;margin-bottom:16px;color:#e0e0f0;
border-left:4px solid #e94560;padding-left:12px}}

/* Charts Grid */
.charts-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:24px;margin-bottom:24px}}
.chart-box{{background:linear-gradient(145deg,#1a1a2e,#16213e);border:1px solid rgba(255,255,255,0.06);
border-radius:12px;padding:24px}}
.chart-box h3{{font-size:1rem;color:#8892b0;margin-bottom:12px}}
canvas{{max-height:300px}}

/* Tables */
.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:0.85rem}}
th{{background:rgba(233,69,96,0.1);color:#e94560;padding:12px 10px;text-align:left;
font-weight:600;position:sticky;top:0;cursor:pointer;user-select:none;white-space:nowrap}}
th:hover{{background:rgba(233,69,96,0.2)}}
td{{padding:10px;border-bottom:1px solid rgba(255,255,255,0.04);color:#c0c0d8}}
tr:hover td{{background:rgba(233,69,96,0.04)}}

/* Tabs */
.tabs{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}}
.tab-btn{{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);
color:#8892b0;padding:8px 20px;border-radius:8px;cursor:pointer;font-size:0.9rem;
transition:all 0.2s;font-family:inherit}}
.tab-btn.active,.tab-btn:hover{{background:rgba(233,69,96,0.15);color:#e94560;border-color:#e94560}}
.tab-content{{display:none}}.tab-content.active{{display:block}}

/* Footer */
.footer{{text-align:center;color:#555;padding:30px;font-size:0.8rem}}
.footer a{{color:#e94560;text-decoration:none}}
</style>
</head>
<body>
<div class="container">

<!-- Header -->
<div class="header">
<h1>🏠 PropertyFinder Egypt — Market Report</h1>
<p>Automated real estate data scraped via Selenium from propertyfinder.eg</p>
<div class="badge">Generated {now}</div>
</div>

<!-- Metrics -->
<div class="metrics">
<div class="metric-card"><div class="value">{len(listings)}</div><div class="label">Rental Listings</div></div>
<div class="metric-card"><div class="value">{fmt_price(avg_price)}</div><div class="label">Avg Price (EGP/mo)</div></div>
<div class="metric-card"><div class="value">{len(projects)}</div><div class="label">Off-Plan Projects</div></div>
<div class="metric-card"><div class="value">{len(agencies)}</div><div class="label">Agencies</div></div>
<div class="metric-card"><div class="value">{fmt_price(total_agents)}</div><div class="label">Total Agents</div></div>
<div class="metric-card"><div class="value">{fmt_price(total_agency_props)}</div><div class="label">Agency Properties</div></div>
</div>

<!-- Charts -->
<div class="charts-grid">
<div class="chart-box"><h3>📍 Listings by Location (Top 10)</h3><canvas id="locChart"></canvas></div>
<div class="chart-box"><h3>💰 Price Distribution (EGP/month)</h3><canvas id="priceChart"></canvas></div>
<div class="chart-box"><h3>🏗 Property Types</h3><canvas id="typeChart"></canvas></div>
<div class="chart-box"><h3>🛏 Bedroom Distribution</h3><canvas id="bedChart"></canvas></div>
</div>

<!-- Data Tabs -->
<div class="section">
<div class="tabs">
<button class="tab-btn active" onclick="showTab('listings')">🏠 Listings ({len(listings)})</button>
<button class="tab-btn" onclick="showTab('projects')">🏗 Projects ({len(projects)})</button>
<button class="tab-btn" onclick="showTab('agencies')">🏢 Agencies ({len(agencies)})</button>
</div>

<div id="listings" class="tab-content active">
<div class="table-wrap"><table>
<thead><tr><th onclick="sortTable(0,'listings')">Title ↕</th><th onclick="sortTable(1,'listings')">Price ↕</th>
<th>Beds</th><th>Baths</th><th>Size (m²)</th><th onclick="sortTable(5,'listings')">Location ↕</th></tr></thead>
<tbody>{listing_rows}</tbody></table></div></div>

<div id="projects" class="tab-content">
<div class="table-wrap"><table>
<thead><tr><th onclick="sortTable(0,'projects')">Project ↕</th><th onclick="sortTable(1,'projects')">Developer ↕</th>
<th>Location</th><th onclick="sortTable(3,'projects')">Starting Price ↕</th>
<th>Status</th><th>Delivery</th><th>Types</th></tr></thead>
<tbody>{project_rows}</tbody></table></div></div>

<div id="agencies" class="tab-content">
<div class="table-wrap"><table>
<thead><tr><th onclick="sortTable(0,'agencies')">Agency ↕</th><th onclick="sortTable(1,'agencies')">Agents ↕</th>
<th onclick="sortTable(2,'agencies')">Total Props ↕</th><th>For Sale</th><th>For Rent</th>
<th>Phone</th></tr></thead>
<tbody>{agency_rows}</tbody></table></div></div>
</div>

<div class="footer">
<p>Data sourced from <a href="https://www.propertyfinder.eg" target="_blank">propertyfinder.eg</a>
&nbsp;·&nbsp; For educational purposes only &nbsp;·&nbsp; Built with Selenium + Python</p>
</div>
</div>

<script>
// Chart colors
const colors = ['#e94560','#f5a623','#4fc3f7','#81c784','#ba68c8','#ff8a65','#4dd0e1','#aed581','#f06292','#7986cb'];
const bgColors = colors.map(c => c + '33');

function mkChart(id, type, labels, data, label) {{
  new Chart(document.getElementById(id), {{
    type: type,
    data: {{
      labels: labels,
      datasets: [{{ label: label, data: data, backgroundColor: bgColors, borderColor: colors, borderWidth: 1.5 }}]
    }},
    options: {{
      responsive: true, plugins: {{ legend: {{ display: type==='pie'||type==='doughnut' }} }},
      scales: type==='pie'||type==='doughnut' ? {{}} : {{
        x: {{ ticks: {{ color: '#8892b0' }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
        y: {{ ticks: {{ color: '#8892b0' }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }}
      }}
    }}
  }});
}}

mkChart('locChart', 'bar', {loc_labels_js}, {loc_values_js}, 'Listings');
mkChart('priceChart', 'bar', {price_labels_js}, {price_values_js}, 'Count');
mkChart('typeChart', 'doughnut', {type_labels_js}, {type_values_js}, 'Types');
mkChart('bedChart', 'bar', {bed_labels_js}, {bed_values_js}, 'Listings');

// Tabs
function showTab(id) {{
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}}

// Sort
function sortTable(col, tabId) {{
  const table = document.querySelector('#'+tabId+' table');
  const rows = Array.from(table.querySelectorAll('tbody tr'));
  const dir = table.dataset.sortDir === 'asc' ? 'desc' : 'asc';
  table.dataset.sortDir = dir;
  rows.sort((a, b) => {{
    let va = a.cells[col].textContent.trim(), vb = b.cells[col].textContent.trim();
    let na = parseFloat(va.replace(/[^0-9.-]/g, '')), nb = parseFloat(vb.replace(/[^0-9.-]/g, ''));
    if (!isNaN(na) && !isNaN(nb)) return dir === 'asc' ? na - nb : nb - na;
    return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
  }});
  const tbody = table.querySelector('tbody');
  rows.forEach(r => tbody.appendChild(r));
}}
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"📊 Report saved → {output_path}")
    return output_path


if __name__ == "__main__":
    report_path = generate_report(data_dir=".")
    print(f"✅ Open {report_path} in your browser to view the report.")
