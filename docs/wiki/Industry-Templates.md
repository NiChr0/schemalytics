# Industry Templates

Schemalytics ships with pre-configured industry taxonomies. When you select an industry during context gathering, it pre-populates suggested entities, analytical goals, and key metrics — giving the LLM a strong starting point for plan generation.

All presets are starting suggestions. You can override any of them interactively.

---

## Available Industries

### E-commerce & Retail

| Sub-type | Key Entities | Analytical Goals |
|----------|-------------|------------------|
| B2C | customers, orders, products, categories, reviews | Revenue reporting, customer cohort analysis, cart abandonment |
| B2B | accounts, contacts, orders, contracts | Account revenue, order frequency, contract renewals |
| Marketplace | sellers, buyers, listings, transactions | GMV, seller performance, buyer retention |
| Subscription | subscribers, plans, payments, renewals | MRR, churn, LTV, trial conversion |

**Key metrics:** revenue, AOV, conversion rate, return rate, CLV, churn

---

### SaaS & Software

| Sub-type | Key Entities | Analytical Goals |
|----------|-------------|------------------|
| B2B | accounts, users, subscriptions, features | MRR/ARR, churn, expansion revenue, feature adoption |
| B2C | users, subscriptions, sessions, events | DAU/MAU, retention, funnel conversion |
| Platform | tenants, apps, API calls, billing | API usage, billing by tenant, marketplace metrics |
| Collaboration | workspaces, members, documents, activity | Engagement, seat utilization, collaboration depth |

**Key metrics:** MRR, ARR, churn rate, NPS, DAU/MAU, feature adoption

---

### Finance & Fintech

| Sub-type | Key Entities | Analytical Goals |
|----------|-------------|------------------|
| Banking | accounts, transactions, customers, branches | Balance trends, transaction volume, product penetration |
| Payments | merchants, transactions, disputes, settlements | Processing volume, authorization rates, fraud |
| Lending | loans, borrowers, payments, defaults | Portfolio performance, default rates, risk metrics |
| Investment | portfolios, holdings, trades, performance | Returns, allocation, risk exposure |
| Crypto | wallets, trades, tokens, protocols | Trading volume, liquidity, DeFi metrics |
| Insurance | policies, claims, premiums, agents | Loss ratio, claims frequency, policy retention |

**Key metrics:** AUM, processing volume, default rate, loss ratio, premium growth

---

### Healthcare

| Sub-type | Key Entities | Analytical Goals |
|----------|-------------|------------------|
| Provider | patients, visits, diagnoses, providers | Patient outcomes, visit volume, readmission rates |
| Telehealth | sessions, patients, providers, prescriptions | Session completion, provider utilization, diagnosis patterns |
| Pharmacy | prescriptions, medications, patients, dispensing | Fill rates, medication adherence, refill patterns |
| Healthtech | users, devices, readings, alerts | Device engagement, health trend analysis |

**Key metrics:** patient volume, readmission rate, medication adherence, HEDIS measures

---

### Media & Entertainment

| Sub-type | Key Entities | Analytical Goals |
|----------|-------------|------------------|
| Streaming | users, content, views, subscriptions | Content performance, viewing hours, churn |
| Gaming | players, sessions, purchases, achievements | DAU, ARPU, retention, monetization |
| Social | users, posts, engagement, follows | Engagement rate, content virality, growth |
| Publishing | articles, authors, readers, subscriptions | Readership, content performance, subscriber LTV |

**Key metrics:** viewing hours, DAU/MAU, ARPU, engagement rate, content completion

---

### Marketing & Advertising

| Sub-type | Key Entities | Analytical Goals |
|----------|-------------|------------------|
| Automation | campaigns, leads, contacts, workflows | Lead conversion, campaign ROI, funnel metrics |
| Ad Networks | advertisers, campaigns, impressions, clicks | CTR, CPM, CPC, ROAS, attribution |
| Email | subscribers, campaigns, sends, clicks | Open rate, CTR, deliverability, list health |
| Influencer | creators, campaigns, posts, reach | Reach, engagement, conversion attribution |

**Key metrics:** CPL, CPC, CPM, ROAS, CTR, conversion rate

---

### Education

| Sub-type | Key Entities | Analytical Goals |
|----------|-------------|------------------|
| K-12 | students, teachers, courses, assessments | Academic performance, attendance, outcomes |
| Higher Ed | students, programs, courses, enrollment | Enrollment trends, graduation rates, career outcomes |
| Online | learners, courses, completions, certifications | Completion rate, learner engagement, content performance |
| Corporate | employees, training, completions, skills | Training completion, skill gap analysis, ROI |

**Key metrics:** completion rate, engagement, learning velocity, certification rate

---

### Logistics & Transportation

| Sub-type | Key Entities | Analytical Goals |
|----------|-------------|------------------|
| Shipping | shipments, carriers, packages, routes | On-time delivery, cost per shipment, carrier performance |
| Warehouse | inventory, orders, locations, movements | Inventory turnover, pick accuracy, storage utilization |
| Rideshare | riders, drivers, trips, routes | Trip completion, driver utilization, fare optimization |
| Delivery | orders, drivers, routes, stops | Delivery time, on-time rate, route efficiency |

**Key metrics:** on-time rate, cost per mile, utilization, OTIF

---

### Hospitality & Travel

**Entities:** guests, bookings, rooms, properties, reservations
**Goals:** occupancy rate, RevPAR, ADR, guest lifetime value
**Key metrics:** occupancy, RevPAR, ADR, repeat booking rate

---

### Real Estate

**Entities:** properties, listings, agents, transactions, leads
**Goals:** transaction volume, days on market, agent performance, lead conversion
**Key metrics:** average sale price, days on market, lead conversion rate

---

### Manufacturing

**Entities:** products, work orders, machines, materials, shipments
**Goals:** production efficiency, OEE, quality metrics, supply chain analysis
**Key metrics:** OEE, yield rate, defect rate, inventory turns

---

### Government & Public Sector

**Entities:** citizens, services, cases, agencies, budgets
**Goals:** service delivery performance, case resolution, budget utilization
**Key metrics:** case resolution time, citizen satisfaction, budget variance

---

## How Templates Are Used

1. **During context gathering** — Schemalytics presents the industry list and pre-fills defaults for the selected sub-type
2. **In LLM prompts** — The selected entities and goals are injected into the planning prompt to guide model naming and metric selection
3. **All overridable** — You can edit entities and goals interactively before the LLM generates the plan

---

## Adding Custom Presets

Industry taxonomy is defined in `schemalytics/industry_taxonomy.py`. To add a new industry or sub-type, add an entry to the `INDUSTRY_TAXONOMY` dictionary following the existing pattern:

```python
"My Industry": {
    "sub_type": {
        "entities": ["entity1", "entity2"],
        "goals": ["analytical goal 1", "analytical goal 2"],
        "metrics": ["metric1", "metric2"],
    }
}
```
