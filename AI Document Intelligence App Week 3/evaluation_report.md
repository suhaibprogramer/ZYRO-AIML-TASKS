# Week 3 — Classifier Evaluation Report
Dataset: 360 samples (Other: 120, Invoice: 120, Resume: 120)
Train/test split: 270 train / 90 test (stratified, 75/25)
## Baseline: Rule-based keyword classifier (Week 1/2)
- Accuracy: 0.833
- Precision (macro): 0.849
- Recall (macro): 0.833
- F1 (macro): 0.832
## Logistic Regression
- Accuracy: 1.000
- Precision (macro): 1.000
- Recall (macro): 1.000
- F1 (macro): 1.000
```
              precision    recall  f1-score   support

     Invoice       1.00      1.00      1.00        30
       Other       1.00      1.00      1.00        30
      Resume       1.00      1.00      1.00        30

    accuracy                           1.00        90
   macro avg       1.00      1.00      1.00        90
weighted avg       1.00      1.00      1.00        90
```
## Linear SVM
- Accuracy: 1.000
- Precision (macro): 1.000
- Recall (macro): 1.000
- F1 (macro): 1.000
```
              precision    recall  f1-score   support

     Invoice       1.00      1.00      1.00        30
       Other       1.00      1.00      1.00        30
      Resume       1.00      1.00      1.00        30

    accuracy                           1.00        90
   macro avg       1.00      1.00      1.00        90
weighted avg       1.00      1.00      1.00        90
```
## Naive Bayes
- Accuracy: 1.000
- Precision (macro): 1.000
- Recall (macro): 1.000
- F1 (macro): 1.000
```
              precision    recall  f1-score   support

     Invoice       1.00      1.00      1.00        30
       Other       1.00      1.00      1.00        30
      Resume       1.00      1.00      1.00        30

    accuracy                           1.00        90
   macro avg       1.00      1.00      1.00        90
weighted avg       1.00      1.00      1.00        90
```
## Model Comparison Summary
| Model | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| Rule-based baseline | 0.833 | 0.849 | 0.833 | 0.832 |
| Logistic Regression | 1.000 | 1.000 | 1.000 | 1.000 |
| Linear SVM | 1.000 | 1.000 | 1.000 | 1.000 |
| Naive Bayes | 1.000 | 1.000 | 1.000 | 1.000 |

**Selected model: Logistic Regression** (highest macro F1 on the test set: 1.000)

Note: this dataset is synthetically generated for demonstration purposes. Real-world performance should be re-evaluated once genuine sample invoices/resumes are collected, as noted in the Week 3 task brief (Step 1).
