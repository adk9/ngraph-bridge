# ==============================================================================
#  Copyright 2018-2019 Intel Corporation
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# ==============================================================================
"""nGraph TensorFlow axpy_variable_update

"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import getpass
import ctypes

import numpy as np
import tensorflow as tf
from tensorflow.python.client import timeline
import json, sys

#import ngraph_bridge

print("TensorFlow version: ", tf.VERSION)

# Setup TensorBoard
graph_location = "/tmp/" + getpass.getuser() + "/tensorboard-logs/test"
print('Saving graph to: %s' % graph_location)
train_writer = tf.summary.FileWriter(graph_location)

def preprocess_fn(image):
    with tf.variable_scope("preprocess"):
        mean = tf.math.reduce_mean(image)
        devs_squared = tf.square(image - mean)
        var = tf.reduce_mean(devs_squared)
        final = (image-mean)/var
    return final

# Configure the session
config = tf.ConfigProto(
    allow_soft_placement=True,
    log_device_placement=False,
    inter_op_parallelism_threads=1,
    graph_options=tf.GraphOptions(
        optimizer_options=tf.OptimizerOptions(
            opt_level=tf.OptimizerOptions.L0,
            do_common_subexpression_elimination=False,
            do_constant_folding=False,
            do_function_inlining=False,
        )))
#config = ngraph_bridge.update_config(config)

# Create session and run
with tf.Session(config=config) as sess:
    # Define the data
    needs_feeddict = sys.argv[0] == 'placeholder'
    inp_data = np.full((2048, 2048), 1.5, dtype=np.float32)
    if (sys.argv[1] == 'constant'):
        a = tf.constant(inp_data, name='alpha')
    elif (sys.argv[1] == 'placeholder'):
        a = tf.placeholder(dtype=np.float32, shape=(2048,2048), name='alpha')
    elif (sys.argv[1] == 'dataset'):
        #dataset = tf.data.Dataset.from_tensor_slices((np.expand_dims(inp_data, 1),))
        dataset = tf.data.Dataset.from_tensor_slices((np.stack([inp_data,inp_data]),))
        dataset = dataset.map(lambda x : tf.squeeze(x))
        dataset = dataset.map(lambda x : preprocess_fn(x))
        dataset = dataset.repeat()
        dataset = dataset.prefetch(5)
        iterator = dataset.make_initializable_iterator()
        sess.run(iterator.initializer)
        a = iterator.get_next()
    else:
        assert False, 'Please provide valid input'
    x = tf.get_variable('x', [2048, 2048], initializer=tf.zeros_initializer)
    y = tf.constant(np.full((2048, 2048), 1.0, dtype=np.float32), name='y')

    c = tf.matmul(a, x)
    axpy = c + y

    train_step = x.assign(axpy)
    with tf.control_dependencies([train_step]):
        train_op = tf.no_op('train_op')




    print("Python: Running with Session")
    options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
    run_metadata = tf.RunMetadata()

    event_times = []
    sess.run(tf.global_variables_initializer())
    summ_writer = tf.summary.FileWriter('summary', sess.graph)
    for i in range(10):
        if needs_feeddict:
            feed_dict = {}
        else:
            feed_dict = {a:inp_data}
        (result_axpy) = sess.run((train_op),
                                options=options,
                                run_metadata=run_metadata, feed_dict = feed_dict),
        print(i)
        event_times.append(timeline.Timeline(run_metadata.step_stats))

    print("Final value: ", x.eval())
    print("Writing event trace")
    with open('tf_event_trace.json', 'w') as f:
        f.write("[\n")
        for event in event_times:
            chrome_trace = event.generate_chrome_trace_format(
                show_dataflow=False)
            parsed_trace = json.loads(chrome_trace)
            for tr in parsed_trace['traceEvents']:
                f.write(json.dumps(tr) + ',\n')

train_writer.add_graph(tf.get_default_graph())
