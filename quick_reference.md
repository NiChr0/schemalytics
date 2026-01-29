# Quick Reference: Interactive Refinement

## 🎯 What It Does

Refine your data model through **natural language conversation** with AI until it's exactly right.

---

## 🚀 Quick Start

```bash
schemalytics generate -c postgresql://localhost/mydb
```

You'll see a detailed plan → give feedback → AI refines → repeat until you approve.

---

## 💬 Example Feedback

### Change Time Grains
```
"make revenue weekly instead of daily"
"change to monthly aggregates"
"weekly is better for our reporting"
```

### Add Tables/Metrics
```
"add customer lifetime value"
"we need a churn rate metric"
"create a table for cohort analysis"
```

### Remove Tables
```
"drop the shipments table"
"we don't need inventory tracking"
"remove all yearly aggregates"
```

### Split/Combine
```
"split customers into B2B and B2C"
"combine products and inventory"
"separate by customer segment"
```

### Modify Attributes
```
"add discount as a measure to orders"
"include shipping in revenue"
"track tax separately"
```

---

## 📋 Commands

| Input | Action |
|-------|--------|
| Natural language | Refine the plan |
| `approve` | Accept plan → generate project |
| `done` | Same as approve |
| `reject` | Cancel generation |
| `cancel` | Same as reject |

---

## 📊 What You'll See

### Initial Plan
```
🔷 SILVER LAYER - DIMENSIONS
dim_customers (SCD Type 2)
  Source: customers
  Grain: one row per customer per valid period
  Foreign Keys:
    → customer_id → referenced by fct_orders
  Columns: customer_id, name, email, segment

📊 SILVER LAYER - FACTS  
fct_orders
  Source: orders
  Grain: one row per order
  Date: order_date
  Foreign Keys:
    → customer_id → dim_customers
    → store_id → dim_stores
  Measures: total_amount, discount, tax
```

### After Feedback
```
CHANGES:
  ✓ Added: dim_customers_b2b
  ✓ Added: dim_customers_b2c
  ✗ Removed: dim_customers
  ⟳ Modified: fct_orders (updated FKs)
```

---

## ⚡ Pro Tips

1. **Be Casual** - "weekly is better" works just as well as "change grain to weekly"

2. **Be Specific** - "add revenue metric" is vague, "add daily revenue by product" is clear

3. **Ask Questions** - AI will explain if something doesn't make sense

4. **Iterate Freely** - No limit on refinements, take your time

5. **Preview Everything** - You see EXACT tables/columns before approval

---

## 🎨 Feedback Patterns

### ✅ Good Feedback
- "make orders weekly"
- "split customers by type"  
- "add lifetime value calculation"
- "remove shipping dimension"

### ⚠️ Vague Feedback
- "make it better" (what should improve?)
- "add more metrics" (which metrics?)
- "fix the customers" (what's wrong?)

### 💡 AI Will Help
If feedback is unclear, AI suggests:
```
Your feedback: "fix customers"

⚠️ What specifically should change about dim_customers?
Options:
- Change SCD type (1 vs 2)
- Add/remove columns
- Split into multiple dimensions
- Change grain
```

---

## 🔄 Typical Session Flow

```
1. Review initial plan (30 seconds)
   ↓
2. "make revenue weekly" (5 seconds)
   ↓
3. See changes, review (15 seconds)
   ↓
4. "add customer segments" (5 seconds)
   ↓
5. See changes, review (15 seconds)
   ↓
6. "looks good!" (5 seconds)
   ↓
7. dbt project generated ✅
```

**Total: ~2 minutes**

---

## 📖 Full Example

See `EXAMPLE_SESSION.md` for a complete 6-iteration refinement session.

---

## 🆘 Troubleshooting

### "I don't see my changes"
- Changes show in DIFF section after each feedback
- Check that feedback was specific enough

### "AI didn't understand"
- Rephrase or be more specific
- AI will ask clarifying questions if confused

### "How do I undo?"
- Just give opposite feedback: "add back the revenue table"
- Future: dedicated undo command

### "Want to start over?"
- Type `reject` then re-run `schemalytics generate`

---

## 🎓 Learning Path

1. **First Try:** Just approve initial plan (see what AI generates)
2. **Second Try:** Make 1-2 simple changes (time grains)
3. **Third Try:** Complex changes (split dimensions, add metrics)
4. **Expert:** Iterative refinement (5+ rounds)

---

## 📚 More Resources

- **INTEGRATION_GUIDE.md** - Technical details
- **EXAMPLE_SESSION.md** - Full walkthrough
- **README.md** - Complete documentation

---

## ✨ Bottom Line

1. AI shows you **exactly** what will be created
2. You refine with **natural language**
3. Iterate until **perfect**
4. Approve and **done!**

**No JSON editing. No manual configs. Just conversation.**