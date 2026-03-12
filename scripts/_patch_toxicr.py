#!/usr/bin/env python3
"""Patch ToxiCR CLEModels.py for Python 3.13 + sklearn 1.8 compatibility.

Replaces sklearn_pandas.DataFrameMapper with manual TF-IDF + numeric feature stacking.
"""
from pathlib import Path

TOXICR_ROOT = Path(__file__).resolve().parent.parent.parent / "ToxiCR"
CLE_PATH = TOXICR_ROOT / "CLEModels.py"

NEW_CLE = r'''# Patched for Python 3.13 / sklearn >= 1.6 compatibility
# Original: Copyright SEAL Lab, Wayne State University, 2022

from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier
from nltk import word_tokenize
from sklearn.model_selection import GridSearchCV
from scipy.sparse import hstack as sp_hstack, csr_matrix
import numpy as np
from pprint import pprint
import nltk

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

mystop_words = ['i', 'me', 'my', 'myself', 'we', 'our', 'ourselves', 'you', 'your',
                'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her',
                'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'themselves',
                'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the',
                'and', 'if', 'or', 'as', 'until', 'of', 'at', 'by', 'between', 'into',
                'through', 'during', 'to', 'from', 'in', 'out', 'on', 'off', 'then', 'once', 'here',
                'there', 'all', 'any', 'both', 'each', 'few', 'more',
                'other', 'some', 'such', 'than', 'too', 'very', 's', 't', 'can', 'will', 'don', 'should', 'now']


class CLEModel:
    def __init__(self, X_train, Y_train, algo="RF", tuning=False):
        self.algo = algo
        self.vectorizer = TfidfVectorizer(tokenizer=word_tokenize, sublinear_tf=True, max_df=0.5,
                                          stop_words=mystop_words, min_df=20)
        self.Y = None
        self.X = None
        self.clf = self.get_classifier()
        self.__prepare_data(X_train, Y_train)
        if tuning:
            self.grid_search_parameter()
        else:
            self.model = self.train()

    def __prepare_data(self, X_train, Y_train):
        self.vectorizer.fit(X_train['message'].astype(str))
        self.Y = np.ravel(Y_train)
        self.X = self._transform(X_train)

    def _transform(self, df):
        tfidf_matrix = self.vectorizer.transform(df['message'].astype(str))
        num_feats = df[['profane_count', 'emoticon_count', 'anger_count']].values.astype(float)
        return sp_hstack([tfidf_matrix, csr_matrix(num_feats)]).tocsr()

    def get_classifier(self):
        algo = self.algo
        if algo == "GBT":
            return GradientBoostingClassifier(n_iter_no_change=5)
        elif algo == "RF":
            return RandomForestClassifier(n_jobs=-1, min_samples_split=5)
        elif algo == "DT":
            return DecisionTreeClassifier()
        elif algo == "SVM":
            return LinearSVC()
        elif algo == "LR":
            return LogisticRegression()

    def grid_search_parameter(self):
        if self.algo == 'RF':
            param_grid = {
                'max_depth': [10, 20, 50, None],
                'criterion': ['gini', 'entropy'],
                'max_features': ['sqrt', 'log2'],
                'min_samples_leaf': [1, 2, 3, 4, 5],
                'min_samples_split': [2, 4, 6, 7, 8, 10],
                'n_estimators': [100, 200, 300, 400, 500, 750, 1000]
            }
        elif self.algo == 'DT':
            param_grid = {
                'splitter': ['best', 'random'],
                'criterion': ['gini', 'entropy'],
                'max_features': ['sqrt', 'log2'],
                'min_samples_leaf': [1, 2, 3, 4, 5],
                'min_samples_split': [2, 4, 6, 7, 8, 10]
            }
        else:
            print("Tuning not implemented for the selected algorithm..")
            exit(0)
        grid_search_model = GridSearchCV(estimator=self.clf, param_grid=param_grid,
                                         cv=10, n_jobs=-1, verbose=3, return_train_score=True)
        grid_search_model.fit(self.X, self.Y)
        pprint(grid_search_model.best_params_)

    def train(self):
        print("Training the model with " + str(len(self.Y)) + " instances and " + str(
            self.X.shape[1]) + " features")
        self.clf.fit(self.X, self.Y)
        print("Model training complete ..")
        return self.clf

    def predict(self, X_test):
        X_test_mapped = self._transform(X_test)
        predictions = self.model.predict(X_test_mapped)
        return np.expand_dims(predictions, 1)
'''

print(f"Patching {CLE_PATH} ...")
CLE_PATH.write_text(NEW_CLE, encoding="utf-8")
print("Done!")
