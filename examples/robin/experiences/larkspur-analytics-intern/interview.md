# Interview record: larkspur-analytics-intern

Written by CV Studio. Questions come from the interviewer agent; `answer:` lines are the user's words, copied exactly. Not a CV source: the facts live in index.md.

## Session 2026-09-20 (add)
status: closed

### Round 1
- [x] 1. What does Larkspur Freight do, how big is it, and which team were you in?
  answer: Regional trucking and warehousing company, about 400 staff. I sat in the operations analytics team, 3 analysts, and reported to the head of operations analytics. 12 week summer internship, full time.
- [x] 2. What did you build or analyse, step by step? Say "I" for your part and "we" for shared work.
  answer: The ops managers tracked late deliveries in an Excel file someone updated by hand every Monday. I wrote the SQL that pulls delivery records from the PostgreSQL warehouse into one clean table, one row per delivery, about 1.2 million rows for 2024 and 2025. Then I built a Power BI dashboard on it with on-time rate by depot, route and week. It refreshes every morning so the Monday update stopped.
- [x] 3. Did any of your work change a decision? What happened after?
  answer: I did an analysis of why deliveries were late. I joined deliveries to driver shift data and found 38% of late deliveries came from routes where loading at the depot took over 45 minutes. I presented it to the head of ops and 4 depot managers in week 9 and two depots changed their loading schedule.
- [x] 4. Which tools did you use?
  answer: SQL (Postgres), Power BI, Excel, and Python with pandas for the late delivery analysis.

### Round 2
- [x] 1. Do you have numbers for the effect of the loading schedule change, and for how many people used the dashboard?
  answer: On-time delivery at those two depots went from 87% to 92% over the next 6 weeks. About 25 weekly users by the end. The Monday Excel update used to take one analyst about 3 hours a week.
- [x] 2. Did anything go wrong along the way, and what did you change?
  answer: First version counted a delivery as late when it was split across two trucks. A depot manager said the numbers looked too high. I fixed the SQL to count by order and added a check against the finance team's monthly delivery count. I also wrote docs for the table so the analysts could keep the SQL going after I left.
- [x] 3. What can be shared publicly on a CV?
  answer: Can name Larkspur and share the percentages. No route names or customer names.
