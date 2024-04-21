# DEMO
Regressive hybrid Recommendation Model: An offline, scalable, supervised recommendation model for user-to-business ratings 

<img width="1728" alt="image" src="https://github.com/zhuyuntong/Rating-Predictive-Hybrid-Recommendation-Model/assets/45145164/53dd222f-89a4-425c-b2bc-27f2395efd8f">


# Model Taxonomy
Hybrid: Supervised learning to combine both approaches:
- Content-based
- Collaborative

Terms:
- Models: ALS Matrix Factorization approach, K-means, XGBRegressor
- Packages/framework: SparkRDD, spark.ml, (gensim, spacy, tensorflow, ... )
- Scaling

# Matrix Factorization using ALS and leveraging Block Matrix Calculation using RDD
![image](https://github.com/zhuyuntong/DEMO/assets/45145164/8ccb6958-9f1b-4c70-ba86-6fec27d7d36d)

# Scaling
![image](https://github.com/zhuyuntong/DEMO/assets/45145164/ed536903-c224-47d7-bc12-899eb20c32f8)

# Usage:
Deploy on your local Env using Dockerfile provided. My workstation is M3 Chip Macbook, you may want to
uncomment the 1st line in Dockerfile for building upon AMD-based architecture.
