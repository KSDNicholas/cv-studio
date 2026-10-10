# Extraction: BrightMart, Data Analyst Intern

status: approved

## JD summary
- company: BrightMart
- role: Data Analyst Intern (intern, internship, location not stated)
- domain: commercial analytics for online grocery retail (delivery performance, basket size, customer retention)
- must: [SQL (sql), BI tool Tableau or Power BI (dashboards, data-visualisation), Python or R for analysis (python, r), clear communication of numbers to non-data stakeholders (stakeholder-management, public-speaking), degree in analytics or similar (education)]
- nice: [dbt or data modelling (data-modelling), A/B testing and basic statistics (statistics), interest in retail or e-commerce (retail, ecommerce)]
- keywords: [SQL, warehouse, dashboards, Power BI, Tableau, Python, delivery performance, customer retention, stakeholders, A/B tests]
- unmatched: [dbt (no evidence), A/B testing (only a planned module, which cannot appear), Tableau (Power BI evidence covers the "Tableau or Power BI" requirement), dataset documentation (not in the master CV, found in experiences/larkspur-analytics-intern/index.md L27)]

## Selected experiences (ordered)

### Data Analyst Intern, Larkspur Freight (May 2026 - Aug 2026)   [score 10/10]
section: Experience
score: tags 6, relevance 3, goals +1, recency +1
why: Evidences all four must-haves (SQL, Power BI, Python, presenting to stakeholders) on delivery performance analysis, plus data modelling.
- Wrote and documented the SQL that pulls about 1.2 million delivery records from the PostgreSQL warehouse into one clean table, checked against the finance team's monthly delivery count. (source: experiences/larkspur-analytics-intern/index.md L21, L27, L41)
- Built a Power BI dashboard of on-time delivery rate that refreshes every morning, reaching about 25 weekly users and replacing a manual Excel update of about 3 hours a week. (source: experiences/larkspur-analytics-intern/index.md L17, L22, L23, L32, L33)
- Joined delivery records to driver shift data in Python (pandas) and found that 38% of late deliveries came from routes with depot loading times over 45 minutes. (source: experiences/larkspur-analytics-intern/index.md L24, L37)
- Presented the finding to the head of operations and 4 depot managers. Two depots then changed their loading schedules, and their on-time delivery rose from 87% to 92% over 6 weeks. (source: experiences/larkspur-analytics-intern/index.md L25, L26, L31)

### Budget Buddy, Personal Project (Jan 2026 - Apr 2026)   [score 7/10]
section: Projects
score: tags 3, relevance 2, goals +1, recency +1
why: Python (pandas) data cleaning and a simple model with held-out accuracy, the basic statistics nice-to-have.
- Built a Python tool, also used by 4 coursemates, that cleans bank CSV exports in pandas by fixing date formats, merging two export formats and removing duplicate rows. (source: experiences/budget-buddy/index.md L14, L16, L20)
- Trained a logistic regression model in scikit-learn on TF-IDF features from about 2,000 hand-labelled transactions, reaching 91% accuracy on a held-out set of 400. (source: experiences/budget-buddy/index.md L21, L22, L28)
- Automated a monthly Excel summary with a chart per category, cutting the time to categorise a month of spending from about 40 minutes to under 5 minutes. (source: experiences/budget-buddy/index.md L24, L29)

### Harbourview Datathon 2026, Harbourview Analytics Society (Mar 2026)   [score 9/10]
section: Hackathons and case competitions
score: tags 6, relevance 2, goals 0, recency +1
why: Python, presenting a recommendation, customer retention analysis in e-commerce, and model evaluation.
- Placed 2nd of 30 teams in a 48-hour datathon on customer retention, predicting which customers of a subscription meal kit company would cancel. (source: experiences/datathon-2026/index.md L14, L15, L25)
- Engineered features such as order frequency, days since last order and skipped weeks for the team's gradient boosting model, which reached an AUC of 0.84 on the organisers' test set. (source: experiences/datathon-2026/index.md L19, L20, L26)
- Built the slides and presented the team's recommendation to offer a discount to customers who skipped 2 weeks in a row, which the judges called the easiest to act on. (source: experiences/datathon-2026/index.md L20, L21, L36)

### Treasurer, Harbourview Analytics Society (Aug 2025 - Present)   [score 6/10]
section: Leadership & Co-Curricular Activities
score: tags 4, relevance 1, goals 0, recency +1
why: SQL, and explaining data to people who do not work with it (teaching SQL to beginners).
- Ran an introductory SQL workshop for first-year members twice, teaching about 60 members in total. (source: experiences/analytics-club-treasurer/index.md L21, L26)
- Moved expense tracking from paper receipts to a shared Google Sheet with a claim form, cutting reimbursement time from about 3 weeks to about 5 days. (source: experiences/analytics-club-treasurer/index.md L20, L25)
- Manages a yearly budget of about 8,000 dollars, mostly datathon sponsorship, for a society of about 150 members, and was re-elected for 2026 to 2027. (source: experiences/analytics-club-treasurer/index.md L14, L15, L19)

## Availability
Available Jan 2027 - Jun 2027

## Education
- BSc Business Analytics, Harbourview University (Aug 2023 - May 2027 (Expected))
- GPA of 3.6 out of 4.0. (source: experiences/harbourview-education/index.md L24)
- Relevant coursework: Database Systems, Data Warehousing, Data Visualisation, Statistics for Business, Regression Analysis, Programming with Python, Machine Learning for Business. (source: experiences/harbourview-education/index.md L18, L19)

## Suggested skills line
SQL (PostgreSQL, SQLite), Power BI, Python (pandas, scikit-learn, LightGBM, openpyxl), Excel, Git, Google Sheets, logistic regression, gradient boosting, feature engineering, TF-IDF text features

## Dropped
- none (every entry outside Archive scored 4 or more and is selected, Archive is empty)

## Open questions
- [x] Only 4 experience and project entries exist, so the draft has 12 bullets, below the usual 14 to 18. Keep it shorter, or add more bullets (for example the Budget Buddy review step for low-confidence predictions, or the treasurer budget of about 8,000 dollars)?
  answer: Add the budget line to Treasurer. Keep Budget Buddy at 3 bullets.
- [x] goals.md says to demote the treasurer work unless the role asks for budgeting or stakeholder skills. The JD asks you to present findings to stakeholders and explain numbers to non-data people, so the draft keeps it with goals 0. Keep it, or drop it?
  answer: Keep it.
- [x] The Larkspur SQL bullet now mentions that you documented the delivery table (index.md L27), to match the JD's "document datasets". This is not in your master CV entry. Keep it?
  answer: Yes, keep it. I did write those docs.
