---
slug: budget-buddy
title: Budget Buddy
organisation: Personal project
dates: Jan 2026 - Apr 2026
type: project
status: condensed
---

# Budget Buddy, Personal project

## Context

- A Python tool that reads my bank's CSV exports and sorts each transaction into a spending category. (Robin, 2026-09-21)
- I built it because I was categorising my spending by hand in a spreadsheet every month. (Robin, 2026-09-21)
- 4 friends from my course use it too. (Robin, 2026-09-21)

## What I did

- I wrote the CSV cleaning in pandas: fixing date formats, merging two bank export formats and removing duplicate rows. (Robin, 2026-09-21)
- I labelled about 2,000 of my own past transactions by hand to make training data. (Robin, 2026-09-21)
- I trained a logistic regression model in scikit-learn on the transaction descriptions, using TF-IDF features. (Robin, 2026-09-21)
- Where the model is less than 70% sure, it asks the user to pick the category, and that answer gets added to the training data. (Robin, 2026-09-21)
- It writes a monthly summary to Excel with a chart per category. (Robin, 2026-09-21)

## Numbers

- 91% accuracy on a held-out set of 400 transactions. (Robin, 2026-09-21)
- Categorising a month of spending went from about 40 minutes by hand to under 5 minutes. (Robin, 2026-09-21)

## Tools

- Python, pandas, scikit-learn, openpyxl, Git. (Robin, 2026-09-21)

## What went wrong and what I changed

- The first model kept putting food delivery into "Transport" because the descriptions mentioned riders. I added more labelled examples of both and accuracy went up. (Robin, 2026-09-21)

## Interview story

## Target role angle

- Data cleaning on messy real data, plus a simple model I can explain. (Robin, 2026-09-21)

## Shareability

- Fine to share. The code is on my GitHub with the transactions removed. (Robin, 2026-09-21)

## Artifact notes

## From seed

(none: not in seed/)

## Open questions
