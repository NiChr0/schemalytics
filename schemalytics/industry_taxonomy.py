"""Industry taxonomy and metadata."""

# Industry taxonomy with predefined entities, goals, and metrics
INDUSTRY_TAXONOMY = {
    "ecommerce_retail": {
        "name": "E-commerce & Retail",
        "sub_industries": {
            "b2c": {
                "name": "Direct to Consumer (B2C)",
                "entities": ["customers", "orders", "products", "order_items", "cart", "reviews", "inventory", "categories"],
                "goals": ["revenue_reporting", "conversion_optimization", "customer_lifetime_value", "inventory_tracking", "product_performance"],
                "metrics": ["gross_merchandise_value", "average_order_value", "conversion_rate", "cart_abandonment_rate", "repeat_purchase_rate"]
            },
            "b2b": {
                "name": "Business to Business (B2B)",
                "entities": ["accounts", "contacts", "orders", "products", "quotes", "contracts", "invoices"],
                "goals": ["account_growth", "deal_pipeline", "contract_management", "revenue_tracking"],
                "metrics": ["account_revenue", "deal_size", "sales_cycle_length", "customer_acquisition_cost"]
            },
            "marketplace": {
                "name": "Multi-vendor Marketplace",
                "entities": ["sellers", "buyers", "products", "orders", "transactions", "reviews", "payouts"],
                "goals": ["gmv_tracking", "seller_performance", "buyer_retention", "commission_tracking"],
                "metrics": ["total_gmv", "take_rate", "active_sellers", "seller_gmv", "buyer_repeat_rate"]
            },
            "subscription": {
                "name": "Subscription Box/Recurring",
                "entities": ["subscribers", "subscriptions", "orders", "products", "shipments", "billing"],
                "goals": ["subscriber_retention", "churn_reduction", "mrr_growth", "ltv_optimization"],
                "metrics": ["monthly_recurring_revenue", "churn_rate", "customer_lifetime_value", "average_subscription_length"]
            }
        }
    },
    "saas_software": {
        "name": "SaaS & Software",
        "sub_industries": {
            "b2b": {
                "name": "Business Software (B2B)",
                "entities": ["accounts", "users", "subscriptions", "features", "usage_events", "billing", "support_tickets"],
                "goals": ["user_activation", "feature_adoption", "expansion_revenue", "churn_prevention"],
                "metrics": ["monthly_recurring_revenue", "annual_recurring_revenue", "net_revenue_retention", "customer_acquisition_cost", "lifetime_value"]
            },
            "b2c": {
                "name": "Consumer Software (B2C)",
                "entities": ["users", "sessions", "subscriptions", "features", "events", "purchases"],
                "goals": ["user_retention", "engagement", "conversion_to_paid", "feature_usage"],
                "metrics": ["daily_active_users", "monthly_active_users", "dau_mau_ratio", "paid_conversion_rate", "churn_rate"]
            },
            "platform": {
                "name": "API/Developer Platform",
                "entities": ["developers", "applications", "api_calls", "subscriptions", "usage_quotas", "billing"],
                "goals": ["api_adoption", "usage_growth", "revenue_tracking", "developer_retention"],
                "metrics": ["total_api_calls", "active_applications", "average_calls_per_app", "api_uptime", "revenue_per_call"]
            },
            "collaboration": {
                "name": "Collaboration & Team Tools",
                "entities": ["workspaces", "users", "teams", "projects", "messages", "files", "activities"],
                "goals": ["team_engagement", "workspace_growth", "feature_adoption", "retention"],
                "metrics": ["daily_active_teams", "messages_per_user", "collaboration_score", "workspace_expansion_rate"]
            }
        }
    },
    "finance_fintech": {
        "name": "Finance & Fintech",
        "sub_industries": {
            "banking": {
                "name": "Banking",
                "entities": ["customers", "accounts", "transactions", "balances", "cards", "loans"],
                "goals": ["transaction_monitoring", "balance_tracking", "fraud_detection", "customer_engagement"],
                "metrics": ["total_deposits", "transaction_volume", "average_balance", "active_accounts", "transaction_count"]
            },
            "payments": {
                "name": "Payment Processing",
                "entities": ["merchants", "transactions", "payments", "fees", "chargebacks", "settlements"],
                "goals": ["transaction_volume_growth", "merchant_retention", "fraud_prevention", "payment_success_rate"],
                "metrics": ["gross_payment_volume", "net_revenue", "transaction_success_rate", "average_transaction_size", "chargeback_rate"]
            },
            "lending": {
                "name": "Lending & Credit",
                "entities": ["borrowers", "loans", "applications", "payments", "credit_scores", "defaults"],
                "goals": ["loan_origination", "default_prediction", "portfolio_performance", "collection_efficiency"],
                "metrics": ["total_loan_volume", "default_rate", "average_loan_size", "approval_rate", "days_to_funding"]
            },
            "investment": {
                "name": "Investment & Trading",
                "entities": ["users", "accounts", "trades", "positions", "portfolios", "transactions"],
                "goals": ["trading_volume", "user_engagement", "portfolio_performance", "revenue_tracking"],
                "metrics": ["total_trading_volume", "active_traders", "average_trade_size", "assets_under_management", "revenue_per_trade"]
            },
            "crypto": {
                "name": "Cryptocurrency",
                "entities": ["users", "wallets", "transactions", "trades", "deposits", "withdrawals"],
                "goals": ["trading_volume", "liquidity_tracking", "user_retention", "transaction_monitoring"],
                "metrics": ["trading_volume", "active_traders", "wallet_balances", "transaction_fees", "deposit_withdrawal_ratio"]
            },
            "insurance": {
                "name": "Insurance",
                "entities": ["policyholders", "policies", "claims", "premiums", "agents", "underwriting"],
                "goals": ["policy_growth", "claims_management", "loss_ratio_tracking", "customer_retention"],
                "metrics": ["total_premiums", "claims_ratio", "policy_count", "average_premium", "retention_rate"]
            }
        }
    },
    "healthcare": {
        "name": "Healthcare",
        "sub_industries": {
            "provider": {
                "name": "Healthcare Provider (Hospitals/Clinics)",
                "entities": ["patients", "appointments", "providers", "diagnoses", "treatments", "billing", "insurance"],
                "goals": ["patient_outcomes", "appointment_efficiency", "revenue_cycle", "provider_utilization"],
                "metrics": ["patient_visits", "no_show_rate", "average_wait_time", "revenue_per_visit", "bed_utilization"]
            },
            "telehealth": {
                "name": "Telehealth/Virtual Care",
                "entities": ["patients", "providers", "appointments", "consultations", "prescriptions", "billing"],
                "goals": ["consultation_volume", "patient_satisfaction", "provider_availability", "revenue_tracking"],
                "metrics": ["total_consultations", "average_consultation_length", "patient_retention", "provider_utilization", "revenue_per_consultation"]
            },
            "pharmacy": {
                "name": "Pharmacy",
                "entities": ["patients", "prescriptions", "medications", "orders", "inventory", "insurance_claims"],
                "goals": ["prescription_volume", "inventory_optimization", "insurance_processing", "patient_adherence"],
                "metrics": ["prescriptions_filled", "inventory_turnover", "claim_approval_rate", "refill_rate", "revenue_per_prescription"]
            },
            "healthtech": {
                "name": "Health Apps & Wellness",
                "entities": ["users", "activities", "health_metrics", "goals", "workouts", "nutrition"],
                "goals": ["user_engagement", "health_outcomes", "retention", "premium_conversion"],
                "metrics": ["daily_active_users", "average_session_length", "goal_completion_rate", "premium_conversion_rate", "health_score_improvement"]
            }
        }
    },
    "media_entertainment": {
        "name": "Media & Entertainment",
        "sub_industries": {
            "streaming": {
                "name": "Video/Music Streaming",
                "entities": ["users", "content", "streams", "playlists", "subscriptions", "devices"],
                "goals": ["user_retention", "content_engagement", "subscription_growth", "viewing_time"],
                "metrics": ["monthly_active_users", "average_watch_time", "content_completion_rate", "churn_rate", "streams_per_user"]
            },
            "gaming": {
                "name": "Gaming",
                "entities": ["players", "sessions", "events", "purchases", "levels", "achievements", "matchmaking"],
                "goals": ["player_retention", "monetization", "engagement", "session_length"],
                "metrics": ["daily_active_users", "monthly_active_users", "arpu", "arppu", "d1_retention", "d7_retention", "session_length"]
            },
            "social": {
                "name": "Social Media",
                "entities": ["users", "posts", "comments", "likes", "follows", "messages", "groups"],
                "goals": ["user_growth", "engagement", "content_virality", "ad_revenue"],
                "metrics": ["daily_active_users", "posts_per_user", "engagement_rate", "viral_coefficient", "time_on_platform"]
            },
            "publishing": {
                "name": "Content Publishing",
                "entities": ["articles", "authors", "readers", "subscriptions", "pageviews", "comments"],
                "goals": ["reader_engagement", "subscription_growth", "content_performance", "ad_revenue"],
                "metrics": ["total_pageviews", "unique_visitors", "average_time_on_page", "subscription_conversion_rate", "articles_per_author"]
            }
        }
    },
    "marketing_advertising": {
        "name": "Marketing & Advertising",
        "sub_industries": {
            "automation": {
                "name": "Marketing Automation",
                "entities": ["contacts", "campaigns", "emails", "workflows", "conversions", "leads"],
                "goals": ["lead_generation", "campaign_performance", "conversion_optimization", "engagement"],
                "metrics": ["total_leads", "email_open_rate", "click_through_rate", "conversion_rate", "lead_to_customer_rate"]
            },
            "advertising": {
                "name": "Advertising Networks",
                "entities": ["advertisers", "campaigns", "ads", "impressions", "clicks", "conversions"],
                "goals": ["campaign_roi", "impression_volume", "click_optimization", "revenue_growth"],
                "metrics": ["total_impressions", "click_through_rate", "cost_per_click", "conversion_rate", "return_on_ad_spend"]
            },
            "email": {
                "name": "Email Marketing",
                "entities": ["subscribers", "campaigns", "emails", "opens", "clicks", "unsubscribes"],
                "goals": ["list_growth", "engagement_optimization", "deliverability", "conversion"],
                "metrics": ["open_rate", "click_through_rate", "unsubscribe_rate", "bounce_rate", "conversion_rate"]
            },
            "influencer": {
                "name": "Influencer Marketing",
                "entities": ["influencers", "campaigns", "brands", "posts", "engagements", "conversions"],
                "goals": ["influencer_performance", "campaign_roi", "brand_awareness", "conversion_tracking"],
                "metrics": ["total_reach", "engagement_rate", "cost_per_engagement", "conversion_rate", "influencer_roi"]
            }
        }
    },
    "education": {
        "name": "Education",
        "sub_industries": {
            "k12": {
                "name": "K-12 Education",
                "entities": ["students", "teachers", "courses", "assignments", "grades", "attendance"],
                "goals": ["student_performance", "attendance_tracking", "course_completion", "teacher_effectiveness"],
                "metrics": ["average_grade", "attendance_rate", "course_completion_rate", "student_teacher_ratio", "assignment_submission_rate"]
            },
            "higher_ed": {
                "name": "Higher Education",
                "entities": ["students", "courses", "enrollments", "grades", "faculty", "departments"],
                "goals": ["enrollment_tracking", "retention", "graduation_rate", "course_performance"],
                "metrics": ["total_enrollment", "retention_rate", "graduation_rate", "average_gpa", "course_completion_rate"]
            },
            "online_courses": {
                "name": "Online Courses & MOOCs",
                "entities": ["students", "courses", "lessons", "completions", "certifications", "purchases"],
                "goals": ["course_completion", "student_engagement", "revenue_growth", "instructor_performance"],
                "metrics": ["total_enrollments", "completion_rate", "average_progress", "revenue_per_student", "student_satisfaction"]
            },
            "corporate": {
                "name": "Corporate Training",
                "entities": ["employees", "courses", "completions", "certifications", "departments", "skills"],
                "goals": ["training_completion", "skill_development", "compliance_tracking", "roi_measurement"],
                "metrics": ["completion_rate", "time_to_complete", "certification_rate", "skills_acquired", "training_hours"]
            }
        }
    },
    "logistics_transportation": {
        "name": "Logistics & Transportation",
        "sub_industries": {
            "shipping": {
                "name": "Shipping & Delivery",
                "entities": ["shipments", "packages", "deliveries", "routes", "drivers", "warehouses"],
                "goals": ["on_time_delivery", "cost_optimization", "route_efficiency", "capacity_utilization"],
                "metrics": ["on_time_delivery_rate", "average_delivery_time", "cost_per_shipment", "packages_per_route", "warehouse_utilization"]
            },
            "warehouse": {
                "name": "Warehouse Management",
                "entities": ["inventory", "locations", "orders", "shipments", "receiving", "picking"],
                "goals": ["inventory_accuracy", "order_fulfillment", "space_utilization", "throughput"],
                "metrics": ["inventory_turnover", "order_fulfillment_time", "picking_accuracy", "storage_utilization", "receiving_efficiency"]
            },
            "rideshare": {
                "name": "Rideshare & Transport",
                "entities": ["riders", "drivers", "trips", "routes", "payments", "ratings"],
                "goals": ["trip_volume", "driver_utilization", "rider_satisfaction", "revenue_growth"],
                "metrics": ["total_trips", "average_trip_distance", "driver_earnings", "rider_rating", "trip_acceptance_rate"]
            },
            "delivery": {
                "name": "Food/Goods Delivery",
                "entities": ["customers", "orders", "couriers", "deliveries", "restaurants", "items"],
                "goals": ["delivery_speed", "order_accuracy", "courier_efficiency", "customer_satisfaction"],
                "metrics": ["average_delivery_time", "on_time_rate", "order_accuracy", "deliveries_per_courier", "customer_rating"]
            }
        }
    },
    "hospitality_travel": {
        "name": "Hospitality & Travel",
        "sub_industries": {
            "hotel": {
                "name": "Hotels & Lodging",
                "entities": ["guests", "reservations", "rooms", "bookings", "payments", "reviews"],
                "goals": ["occupancy_rate", "revenue_per_room", "guest_satisfaction", "booking_efficiency"],
                "metrics": ["occupancy_rate", "average_daily_rate", "revenue_per_available_room", "booking_lead_time", "guest_rating"]
            },
            "booking": {
                "name": "Travel Booking",
                "entities": ["travelers", "bookings", "flights", "hotels", "packages", "payments"],
                "goals": ["booking_volume", "conversion_rate", "revenue_growth", "customer_retention"],
                "metrics": ["total_bookings", "average_booking_value", "conversion_rate", "cancellation_rate", "repeat_booking_rate"]
            },
            "restaurant": {
                "name": "Restaurant POS",
                "entities": ["orders", "customers", "menu_items", "tables", "payments", "staff"],
                "goals": ["table_turnover", "average_check_size", "menu_optimization", "labor_efficiency"],
                "metrics": ["revenue_per_table", "table_turnover_rate", "average_check_size", "popular_items", "labor_cost_percentage"]
            },
            "rental": {
                "name": "Vacation Rentals",
                "entities": ["properties", "guests", "bookings", "reviews", "payments", "owners"],
                "goals": ["occupancy_rate", "revenue_per_property", "guest_satisfaction", "owner_retention"],
                "metrics": ["occupancy_rate", "average_nightly_rate", "revenue_per_property", "booking_lead_time", "guest_rating"]
            }
        }
    },
    "real_estate": {
        "name": "Real Estate",
        "sub_industries": {
            "residential": {
                "name": "Residential Real Estate",
                "entities": ["properties", "buyers", "sellers", "agents", "listings", "transactions"],
                "goals": ["sales_volume", "listing_conversion", "agent_performance", "market_trends"],
                "metrics": ["total_sales_volume", "average_sale_price", "days_on_market", "listing_to_sale_ratio", "agent_commissions"]
            },
            "commercial": {
                "name": "Commercial Real Estate",
                "entities": ["properties", "tenants", "leases", "landlords", "spaces", "payments"],
                "goals": ["occupancy_rate", "lease_performance", "tenant_retention", "revenue_tracking"],
                "metrics": ["occupancy_rate", "average_lease_value", "tenant_turnover_rate", "rental_income", "lease_renewal_rate"]
            },
            "management": {
                "name": "Property Management",
                "entities": ["properties", "tenants", "leases", "maintenance", "payments", "work_orders"],
                "goals": ["occupancy_optimization", "maintenance_efficiency", "tenant_satisfaction", "revenue_collection"],
                "metrics": ["occupancy_rate", "rent_collection_rate", "maintenance_response_time", "tenant_retention_rate", "net_operating_income"]
            }
        }
    },
    "manufacturing": {
        "name": "Manufacturing",
        "sub_industries": {
            "production": {
                "name": "Manufacturing Production",
                "entities": ["products", "production_runs", "materials", "machines", "quality_checks", "inventory"],
                "goals": ["production_efficiency", "quality_control", "downtime_reduction", "inventory_optimization"],
                "metrics": ["units_produced", "production_yield", "defect_rate", "machine_utilization", "cycle_time"]
            },
            "supply_chain": {
                "name": "Supply Chain",
                "entities": ["suppliers", "orders", "shipments", "inventory", "warehouses", "demand"],
                "goals": ["supplier_performance", "inventory_optimization", "demand_forecasting", "cost_reduction"],
                "metrics": ["supplier_on_time_rate", "inventory_turnover", "stockout_rate", "lead_time", "supply_chain_cost"]
            },
            "inventory": {
                "name": "Inventory Management",
                "entities": ["items", "locations", "stock", "movements", "orders", "suppliers"],
                "goals": ["stock_optimization", "turnover_improvement", "shortage_prevention", "cost_control"],
                "metrics": ["inventory_turnover", "stock_accuracy", "carrying_cost", "stockout_frequency", "order_fulfillment_rate"]
            }
        }
    },
    "human_resources": {
        "name": "Human Resources",
        "sub_industries": {
            "hris": {
                "name": "HR Management",
                "entities": ["employees", "departments", "positions", "performance_reviews", "attendance", "benefits"],
                "goals": ["employee_retention", "performance_tracking", "headcount_planning", "compliance"],
                "metrics": ["headcount", "turnover_rate", "average_tenure", "performance_scores", "time_to_fill"]
            },
            "recruiting": {
                "name": "Recruiting & ATS",
                "entities": ["candidates", "jobs", "applications", "interviews", "offers", "hires"],
                "goals": ["time_to_hire", "candidate_quality", "recruiter_efficiency", "offer_acceptance"],
                "metrics": ["time_to_hire", "applicants_per_job", "interview_to_offer_ratio", "offer_acceptance_rate", "cost_per_hire"]
            },
            "payroll": {
                "name": "Payroll",
                "entities": ["employees", "paychecks", "hours", "deductions", "taxes", "benefits"],
                "goals": ["payroll_accuracy", "compliance", "processing_efficiency", "cost_tracking"],
                "metrics": ["total_payroll_cost", "average_salary", "overtime_hours", "payroll_errors", "processing_time"]
            },
            "talent": {
                "name": "Talent Marketplace",
                "entities": ["freelancers", "projects", "contracts", "deliverables", "payments", "reviews"],
                "goals": ["freelancer_utilization", "project_completion", "client_satisfaction", "revenue_growth"],
                "metrics": ["active_freelancers", "project_completion_rate", "average_project_value", "freelancer_rating", "repeat_client_rate"]
            }
        }
    },
    "nonprofit_government": {
        "name": "Nonprofit & Government",
        "sub_industries": {
            "nonprofit": {
                "name": "Nonprofit",
                "entities": ["donors", "donations", "campaigns", "programs", "beneficiaries", "volunteers"],
                "goals": ["fundraising_growth", "donor_retention", "program_impact", "volunteer_engagement"],
                "metrics": ["total_donations", "donor_retention_rate", "average_donation_size", "program_participants", "volunteer_hours"]
            },
            "government": {
                "name": "Government Services",
                "entities": ["citizens", "services", "applications", "cases", "payments", "appointments"],
                "goals": ["service_delivery", "application_processing", "citizen_satisfaction", "efficiency"],
                "metrics": ["applications_processed", "average_processing_time", "service_completion_rate", "citizen_satisfaction_score", "cost_per_service"]
            }
        }
    },
    "other": {
        "name": "Other/Custom",
        "sub_industries": {
            "generic": {
                "name": "Generic Business",
                "entities": ["records", "events", "users", "transactions"],
                "goals": ["reporting", "analytics", "tracking"],
                "metrics": ["record_count", "daily_activity", "user_engagement"]
            }
        }
    }
}