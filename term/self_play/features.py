import tensorflow as tf


ACTIONS = [
    ('fold',),
    ('check', 'fold'),
    ('check', 'call'),
    ('bet', 'fold'),
    ('bet', 'raise'),
    ('allin',),
]

FEATURES = {
    'p1_status': tf.contrib.layers.sparse_column_with_keys(
        column_name="player_1_status", keys=['out', 'fold', 'in', 'allin']),
    'p2_status': tf.contrib.layers.sparse_column_with_keys(
        column_name="player_2_status", keys=['out', 'fold', 'in', 'allin']),
    'p3_status': tf.contrib.layers.sparse_column_with_keys(
        column_name="player_3_status", keys=['out', 'fold', 'in', 'allin']),
    'p4_status': tf.contrib.layers.sparse_column_with_keys(
        column_name="player_4_status", keys=['out', 'fold', 'in', 'allin']),
    'p5_status': tf.contrib.layers.sparse_column_with_keys(
        column_name="player_5_status", keys=['out', 'fold', 'in', 'allin']),
    'p6_status': tf.contrib.layers.sparse_column_with_keys(
        column_name="player_6_status", keys=['out', 'fold', 'in', 'allin']),
    'p7_status': tf.contrib.layers.sparse_column_with_keys(
        column_name="player_7_status", keys=['out', 'fold', 'in', 'allin']),
    'p8_status': tf.contrib.layers.sparse_column_with_keys(
        column_name="player_8_status", keys=['out', 'fold', 'in', 'allin']),
}
