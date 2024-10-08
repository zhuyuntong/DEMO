import json
import pandas as pd
import numpy as np
from collections import Counter
import hashlib
from sklearn.preprocessing import LabelEncoder
from hashlib import md5
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import PowerTransformer


def read_json_data(file_path, extract_func, sc):
    return sc.textFile(file_path).map(extract_func)


# user.json Parser
# RDD ===> pandas df
def transform_user_data(user_json):
    user = json.loads(user_json)
    user_data = {
        'user_id': user['user_id'],
        'average_stars': user['average_stars'],
        'user_review_count': user['review_count'],
        'fans': user['fans'],
        'useful': user['useful'],
        'funny': user['funny'],
        'cool': user['cool'],
        'num_interactions': sum([user.get(key, 0) for key in ['useful', 'funny', 'cool']]),
        'yelping_since': int(2024) - int(user.get('yelping_since', '2024').split('-')[0]),
        'friends_count': 0 if user['friends'] == 'None' else len(user['friends'].split(',')),
        'elite_years': 0 if user['elite'] == 'None' else len((user['elite'].split(','))),
        'compliments': sum([user[key] for key in user if key.startswith('compliment_')]),
        ######### not sure if works
        'compliment_hot': user['compliment_hot'],
        'compliment_more': user['compliment_more'],
        'compliment_profile': user['compliment_profile'],
        'compliment_cute': user['compliment_cute'],
        'compliment_list': user['compliment_list'],
        'compliment_note': user['compliment_note'],
        'compliment_plain': user['compliment_plain'],
        'compliment_cool': user['compliment_cool'],
        # 'compliment_funny': user['compliment_funny'],
        'compliment_writer': user['compliment_writer'],
        'compliment_photos': user['compliment_photos'],
    }
    return user_data


# buiness.json Parser
# RDD ===> pandas df
def transform_business_data(business_json):
    business = json.loads(business_json)
    return {
        'business_id': business['business_id'],
        'bus_stars': business['stars'],
        'bus_review_count': business['review_count'],
        'categories': business['categories'],
        'city': business['city'],
        'is_open': business['is_open'],
    }


## TODO: TEXT-Based Analysis
# review.json Parser
# RDD ===> dict ===> FeatureProcessor()
def extract_review_data(review_json):
    try:
        review = json.loads(review_json)
        # Process 'date' to datetime object
        review_date_str = review.get('date', '2024-01-01')
        review_date = datetime.strptime(review_date_str, "%Y-%m-%d")

        # Calculate total ufc (user feedback count)
        pos_total = sum([review.get(key, 0) for key in ['cool']])
        neg_total = sum([review.get(key, 0) for key in ['funny', 'useful']])
        ufc_total = pos_total + neg_total

        # calculate based on time average
        current_date = datetime.strptime('2024-01-01', "%Y-%m-%d")
        years_since_review = max((current_date - review_date).days / 365, 1)
        ufc_count_per_year = ufc_total / years_since_review

        return {
            'review_id': review['review_id'],
            # 'review_date': review_date,
            'user_id': review['user_id'],
            'business_id': review['business_id'],
            'stars': review['stars'],
            # 'text': review.get('text', ""),
            'useful': review['useful'],
            # 'pos_count': pos_total,
            # 'neg_count': neg_total,
            'ufc_count': ufc_total,
            'ufc_count_per_year': ufc_count_per_year,
        }
    except json.JSONDecodeError:
        return None


def process_categories(categories):
    if pd.isnull(categories):
        return []
    categories = str(categories)

    cleaned_categories = categories.replace("&", " ").replace("/", " ").replace("(", "").replace(")", "").replace("  ", "")
    return [h.strip().lower() for h in cleaned_categories.split(",")]


from MF import decompose_matrix_factorization_als, predict_aff_score_als


class FeatureProcessor:
    def __init__(self, sc, data_folder_path, user_df, business_df, review_df):
        self.user_df, self.business_df, self.review_df = self._process_and_combine_remaining_features(
            user_df, business_df, review_df
        )
        self._encode_bus_city()  # modify biz_df
        ################################################################
        (
            self.user_features_bcast,
            self.biz_features_bcast,
            self.user_ids,
            self.business_ids,
            # self.user_features_rdd,
            # self.biz_features_rdd,
            self.user_ids_bcast,
            self.business_ids_bcast,
        ) = decompose_matrix_factorization_als(sc, data_folder_path)
        ################################################################
        pass

    def _encode_bus_city(self):
        # 对城市进行标签编码
        lbe_city = LabelEncoder()
        self.business_df['city_encoded'] = lbe_city.fit_transform(self.business_df['city'])

    def _create_df_conn1(self):
        remaining_business = (
            self.business_df[['business_id', 'categories']]
            .explode('categories')
            .dropna(subset=['categories'])
            .assign(type=lambda df: df['categories'].apply(lambda x: md5(x.encode('UTF-8')).hexdigest()))
            .rename(columns={'business_id': 'bid_cat'})
        )

        remaining_business['bid_cat'] = remaining_business['bid_cat'] + '_bid'
        type_res = remaining_business['type'].tolist()
        id_cf = remaining_business['bid_cat'].tolist()
        return type_res, id_cf

    def _process_unique_category(self):
        self.business_df['categories'] = self.business_df['categories'].apply(process_categories)
        type_res, id_cf = self._create_df_conn1()

        # Create DataFrames
        df_conn1 = pd.DataFrame({"type": type_res, "bid_cat": id_cf})
        add_info = list(set(id_cf))
        df_conn_add = pd.DataFrame({"type": add_info, "bid_cat": add_info})
        df_conn = pd.concat([df_conn1, df_conn_add])

        return df_conn

    def _process_and_combine_remaining_features(self, user_df, business_df, review_df):
        """
        Process features for user and business dataframes based on review data.

        Args:
        user_df (pd.DataFrame): DataFrame containing user data.
        business_df (pd.DataFrame): DataFrame containing business data.
        review_df (pd.DataFrame): DataFrame containing review data.

        Returns:
        tuple: tuple containing:
            user_df (pd.DataFrame): Updated DataFrame with new user features.
            business_df (pd.DataFrame): Updated DataFrame with new business features.
        """

        # User features total_ufc
        total_ufc_per_year = review_df.groupby('user_id')['ufc_count_per_year'].sum().reset_index()
        total_ufc_per_year.rename(columns={'ufc_count_per_year': 'total_ufc_count_per_year'}, inplace=True)
        user_df = user_df.merge(total_ufc_per_year, on='user_id', how='left')
        user_df['total_ufc_count_per_year'] = user_df['total_ufc_count_per_year'].fillna(0)  # Handling cold start for users

        # User features avg_ufc
        avg_ufc_per_review = review_df.groupby('user_id')['ufc_count'].mean().reset_index()
        avg_ufc_per_review.rename(columns={'ufc_count': 'avg_ufc_count_per_review'}, inplace=True)
        user_df = user_df.merge(avg_ufc_per_review, on='user_id', how='left')
        user_df['avg_ufc_count_per_review'] = user_df['avg_ufc_count_per_review'].fillna(0)  # Handling cold start for users
        return (user_df, business_df, review_df)

    def ___encode_open_status(self):
        self.business_df = pd.get_dummies(self.business_df, columns=["is_open"])

    def ___merge_category_features_batch(self, df):
        # for the category value bug (0,0,0,0..) fixing, reverse if accuracy got worse
        df['business_id'] = df['business_id'].apply(lambda x: x + '_bid')
        df['user_id'] = df['user_id'].apply(lambda x: x + '_uid')

        # merge 每个user, 商家ID（bid_cat）的所有类别特征向量的平均值
        ## business
        df_with_cat_features = df.merge(self.category_features, left_on='business_id', right_on='bid_cat', how='left')
        df_with_cat_features.drop('bid_cat', axis=1, inplace=True)
        ## user
        df_with_cat_features = df_with_cat_features.merge(self.df_embedding, left_on="user_id", right_on="id", how="left")
        df_with_cat_features.drop('user_id', axis=1, inplace=True)
        return df_with_cat_features

    def ___merge_embeddings(self, embedding_file):
        # 合并df_conn和df_embedding
        # 假设df_embedding中的类别哈希值在列'id'中，特征向量在其他列
        # 删除非数值列并处理缺失值
        df_embedding = pd.read_csv(embedding_file)

        catfeatures = self.df_conn.merge(df_embedding, left_on='type', right_on='id', how='left')
        catfeatures = catfeatures.drop(["type", "id"], axis=1).fillna(0)

        # 聚合操作 - 计算每个商家ID（bid_cat）的所有类别特征向量的平均值
        catfeatures = catfeatures.groupby('bid_cat').mean()
        catfeatures.reset_index(inplace=True)
        return catfeatures

    def ___process_reviews_features(self, review_df):
        # 计算每个business_id的平均useful评分
        review_grouped = review_df.groupby('business_id')['useful'].mean().reset_index()
        review_grouped.columns = ['business_id', 'avg_useful_score']
        return review_grouped

    # RDD-based: given (user, biz) pairs files (yelp_train.csv), return w/ all features columns attached
    def process_all_features(self, sc, train_df, pair_file_path='../yelp_combined.csv'):
        final_scores_rdd = predict_aff_score_als(
            sc,
            self.user_features_bcast,
            self.biz_features_bcast,
            self.user_ids,
            self.business_ids,
            # self.user_features_rdd,
            # self.biz_features_rdd,
            self.user_ids_bcast,
            self.business_ids_bcast,
            pair_file_path,
        )  # cached already

        # FIXME tip.json load method: RDD ==> Pandas (alleviate OOM Issue)
        scores_df = pd.DataFrame(final_scores_rdd.collect(), columns=['user_business_pair', 'score'])
        final_scores_rdd.unpersist()

        scores_df[['user_id', 'business_id']] = pd.DataFrame(scores_df['user_business_pair'].tolist(), index=scores_df.index)
        scores_df.drop('user_business_pair', axis=1, inplace=True)

        final_train_df = pd.merge(train_df, scores_df, on=['user_id', 'business_id'], how='left')
        final_train_df = pd.merge(final_train_df, self.user_df, on='user_id', how='left')
        final_train_df = pd.merge(final_train_df, self.business_df, on='business_id', how='left')

        def inverse_log_transform(normalized_score):
            """Reverse Log-Trans to Original Affinity Scores 转换标准化后的评分到原始亲和力分数"""
            max_log = np.log(284 + 1)  # Highest implicit interaction counts
            min_log = np.log(1 + 1)  # Lowest
            return np.exp((normalized_score - 1) / 4 * (max_log - min_log) + min_log) - 1

        final_train_df['affinity_score'] = final_train_df['score'].apply(
            lambda x: 50 * inverse_log_transform(x) if pd.notnull(x) else 0
        )

        final_train_df.drop(['categories', 'city'], axis=1, errors='ignore', inplace=True)

        return final_train_df

        '''
        # FIXME

        # BUG
        # 将Pandas DataFrame转换为Spark RDD
        train_rdd = sc.parallelize(train_df.to_dict('records'))
        user_rdd = sc.parallelize(self.user_df.to_dict('records'))
        business_rdd = sc.parallelize(self.business_df.to_dict('records'))
        # BUG

        # 提取出user_id, business_id作为key, 其他信息作为value的键值对
        user_info_rdd = user_rdd.map(lambda x: (x['user_id'], x))
        business_info_rdd = business_rdd.map(lambda x: (x['business_id'], x))

        user_rdd.unpersist()
        business_rdd.unpersist()
        # 将train_rdd与user_info_rdd和business_info_rdd信息进行左外合并
        # 使用leftOuterJoin保证基数不变
        train_user_rdd = (
            train_rdd.map(lambda x: (x['user_id'], x))
            .leftOuterJoin(user_info_rdd)
            .map(
                lambda x: (
                    x[1][0]['business_id'],
                    {**x[1][0], **(x[1][1] if x[1][1] else {})},
                )  # Merge user info or add empty if not present
            )
        )

        train_rdd.unpersist()

        # 合并business信息，再次使用左外合并
        final_train_rdd = train_user_rdd.leftOuterJoin(business_info_rdd).map(
            lambda x: {**x[1][0], **(x[1][1] if x[1][1] else {})}  # Merge business info or add empty if not present
        )

        user_info_rdd.unpersist()
        business_info_rdd.unpersist()
        train_user_rdd.unpersist()

        # 合并final_scores到train_df，使用左外合并
        def inverse_log_transform(normalized_score):
            """逆向转换标准化后的评分到原始亲和力分数"""
            max_log = np.log(284 + 1)  # 284是统计得出的最高的implicit互动次数
            min_log = np.log(1 + 1)  # 1是最低次数 (tip中都至少互动过一次)
            return np.exp((normalized_score - 1) / 4 * (max_log - min_log) + min_log) - 1

        final_rdd = (
            final_train_rdd.map(lambda x: ((x['user_id'], x['business_id']), x))  # FIXME: original: final_train_rdd
            .leftOuterJoin(scores_kv_rdd)
            .map(
                lambda x: {
                    **x[1][0],
                    'affinity_score': (
                        float(50 * inverse_log_transform(x[1][1])) if x[1][1] else 0
                    ),  # NOTE: FIXME: Test play with x[1][1]
                }  # Add affinity score or 0 if not present
            )
        )
        final_train_rdd.unpersist()
        scores_kv_rdd.unpersist()

        final_rdd = final_rdd.map(lambda x: {key: val for key, val in x.items() if key not in ['categories', 'city']})

        return final_rdd
    '''

    # return mapped Past reviews w/ category attached, prepare for KMeans user clustering
    def map_reviews_with_categories(self):
        df_conn = self._process_unique_category()
        return integrate_mapping_user_bus_cat_data(df_conn, self.business_df, self.review_df)


from utils import integrate_mapping_user_bus_cat_data


def inverse_log_transform(normalized_score):
    """逆向转换标准化后的评分到原始亲和力分数"""
    max_log = np.log(284 + 1)  # 284 is the max.Interaction Count from tip.json
    min_log = np.log(1 + 1)
    return np.exp((normalized_score - 1) / 4 * (max_log - min_log) + min_log) - 1


###############################
'''
# def md5_hash(s):
#     hash_val = hashlib.md5(s.encode()).hexdigest()[:32]
#     return hash_val


# def clean_categories(categories):
#     if categories:
#         # 替换特殊字符并拆分为单独的类别
#         return [
#             cat.strip().lower()
#             for cat in categories.replace("&", " ")
#             .replace("/", " ")
#             .replace("(", "")
#             .replace(")", "")
#             .replace("  ", " ")
#             .split(",")
#         ]
#     else:
#         return []


# def hash_categories(business_id, categories):
#     cleaned_cats = clean_categories(categories)
#     return [md5_hash(cat) for cat in cleaned_cats]


# def process_all_features(self, train_df):
#     df = train_df.merge(self.user_df, on='user_id', how='left')
#     df = df.merge(self.business_df, on='business_id', how='left')
#     df = df.merge(self.review_df, on='business_id', how='left')
#     # df.drop(columns=['categories', 'city'], inplace=True) # revert categories back if later use NLP

#     # add side info
#     # train_df_with_features = self.merge_category_features_batch(df)
#     # return train_df_with_features
#     return df
'''


## Archived
## RDD ==> dict
def ___extract_business_data(business_json):
    business = json.loads(business_json)
    return (
        business['business_id'],
        {
            'bus_stars': business['stars'],
            'bus_review_count': business['review_count'],
            'categories': business['categories'],
            'city': business['city'],
            'is_open': business['is_open'],
        },
    )
