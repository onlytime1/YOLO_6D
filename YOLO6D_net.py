import tensorflow as tf
import numpy as np
from utils import *
import sys
import config as cfg

"""
5BTM 51C9 3791 5TKL
This is the script to try to reproduce YOLO-6D
input: a mini-batch of images
train:

"""

class YOLO6D_net:

    Batch_Size = cfg.BATCH_SIZE
    WEIGHT_DECAY = cfg.WEIGHT_DECAY
    MAX_PADDING = cfg.MAX_PAD
    EPSILON = cfg.EPSILON
    learning_rate = cfg.LEARNING_RATE
    optimizer = None
    loss = None
    disp = cfg.DISP
    param_num = 0
    boxes_per_cell = cfg.BOXES_PER_CELL
    image_size = cfg.IMAGE_SIZE

    num_class = 0
    Batch_Norm = cfg.BATCH_NORM
    ALPHA = cfg.ALPHA
    cell_size = cfg.CELL_SIZE
    num_coord = cfg.NUM_COORD  ## 9 points, 8 corners + 1 centroid

    obj_scale = cfg.CONF_OBJ_SCALE
    noobje_scale = cfg.CONF_NOOBJ_SCALE
    class_scale = cfg.CLASS_SCALE
    coord_scale = cfg.COORD_SCALE

    def __init__(self):
        """
        placeholder定义输入
        """
        self.input_images = tf.placeholder(tf.float32, [None, self.image_size, self.image_size, 3], name='Input')
        self.logit = self._build_net(self.input_images)

        """
        Input labels struct:
        [
            responsible: 1
            9 points coord: 18
            confidence: 1
            class number: num_class
        ]
        """
        self.boundry_1 = 9 * 2 * self.boxes_per_cell   ## Seperate coordinates
        self.boundry_2 = self.num_class
        self.labels = tf.placeholder(tf.float32, [None, self.cell_size, self.cell_size, 19 + self.num_class + 1], name='Labels')  #labels should have 1-d tensor to be responsible
        self.off_set = tf.transpose(np.reshape(np.array(
                                    [np.arange(self.cell_size)] * self.cell_size * self.boxes_per_cell),  ## array shape
                                    (1, self.cell_size, self.cell_size)),   ## reshape array
                                    (1, 2, 0))   ## transpose array
        self.loss = self.loss_layer(self.logit, self.labels)
        self.total_loss = tf.losses.get_total_loss()


    def _build_net(self, input_size):
        if self.disp:
            print("-----building network-----")
        self.x = self.conv(self.input_images, 3, 1, 32, num=1)
        self.x = self.max_pool_layer(self.x, name='MaxPool1')
        self.x = self.conv(self.x, 3, 1, 64, num=2)
        self.x = self.max_pool_layer(self.x, name='MaxPool2')
        self.x = self.conv(self.x, 3, 1, 128, num=3)
        self.x = self.conv(self.x, 1, 1, 64, num=4)
        self.x = self.conv(self.x, 3, 1, 128, num=5)
        self.x = self.max_pool_layer(self.x, name='MaxPool3')
        self.x = self.conv(self.x, 3, 1, 256, num=6)
        self.x = self.conv(self.x, 1, 1, 128, num=7)
        self.x = self.conv(self.x, 3, 1, 256, num=8)
        self.x = self.max_pool_layer(self.x, name='MaxPool4')
        self.x = self.conv(self.x, 3, 1, 512, num=9)
        self.x = self.conv(self.x, 1, 1, 256, num=10)
        self.x = self.conv(self.x, 3, 1, 512, num=11)
        self.x = self.conv(self.x, 1, 1, 256, num=12)
        self.x = self.conv(self.x, 3, 1, 512, num=13)
        self.x_ps = self.conv(self.x, 1, 1, 64, num=14)    #add a pass through layer
        self.x_ps = self.conv(self.x_ps, 3, 2, 256, num=15)   
        self.x = self.max_pool_layer(self.x, name='MaxPool5')    #continue straight layer
        self.x = self.conv(self.x, 3, 1, 1024, num=16)
        self.x = self.conv(self.x, 1, 1, 512, num=17)
        self.x = self.conv(self.x, 3, 1, 1024, num=18)
        self.x = self.conv(self.x, 1, 1, 512, num=19)
        self.x = self.conv(self.x, 3, 1, 1024, num=20)
        self.x = self.conv(self.x, 3, 1, 1024, num=21)
        self.x = self.conv(self.x, 3, 1, 1024, num=22)
        self.x = self.merge_layer(self.x, self.x_ps, name='Merge')
        self.x = self.conv(self.x, 3, 1, 1024, num=23)
        self.x = self.conv(self.x, 1, 1, 18 + self.num_class, num=24)
        return self.x

    def conv(self, x, kernel_size, strides, filters, num, pad='SAME', scope='Conv_layer'):
        """
        Conv ==> ReLU ==> Batch_Norm
        """
        x = self.conv_layer(x, kernel_size, strides, filters, pad='SAME', name='Conv:{0}'.format(num))
        x = self.activation(x)
        if self.Batch_Norm:
            x = self.bn(x)
        return x

    def conv_layer(self, x, kernel_size, strides, filters, name, pad='SAME'):
        x_shape = x.get_shape()
        x_channels = x_shape[3].value
        weight_shape = [kernel_size, kernel_size, x_channels, filters]
        bias_shape = [filters]
        weight = self._get_variable(name, weight_shape, initializer=tf.truncated_normal_initializer)
        bias = self._get_variable(name, bias_shape, initializer=tf.constant(0.0))
        y = tf.nn.conv2d(x, weight, strides=strides, padding=pad, name=name)
        y = tf.add(y, bias, name=name)
        return y

    def merge_layer(self, x1, x2, name):
        """
        input are 2 tensors from different conv_layer
        """
        x_list = [x1, x2]
        y = tf.concat(3, x_list, name=name)
        return y

    def max_pool_layer(self, x, name):
        return tf.nn.max_pool(x, ksize=[1,2,2,1], strides=[1,2,2,1], padding=self.MAX_PADDING, name=name)

    def bn(self, x, name='BN'):
        axes = [d for d in range(len(x.get_shape()))]
        gamma = self._get_variable('gamma', [], initializer=tf.constant_initializer(1.0))
        beta  = self._get_variable('beta', [], initializer=tf.constant_initializer(0.0))
        x_mean, x_variance = tf.nn.moments(x, axes)
        y = tf.nn.batch_normalization(x, x_mean, x_variance, beta, gamma, self.EPSILON, name=name)
        return y

    def activation(self, x, name='activation_func'):
        return tf.nn.relu(x, name='relu')

    def _get_variable(self, name, shape, initializer):
        """
        创建一个函数获取变量，方便进行正则化处理等
        """
        param = 1
        for i in range(0, len(shape)):
            param *= shape[i]
        self.param_num += param

        if self.WEIGHT_DECAY > 0:
            regularizer = tf.contrib.layers.l2_regularizer(self.WEIGHT_DECAY)
        else:
            regularizer = None
        
        return tf.get_variable(name, shape = shape, regularizer=regularizer, initializer=initializer)

    def get_optimizer(self):
        ##choose an optimizer to train the network
        self.optimizer = tf.train.AdamOptimizer(learning_rate=self.learning_rate).minimize(self.loss)

    def calcu_iou(self, boxes1, boxes2, scope='iou'):
        """
        calculate 2 boxes' iou

        Args: 
            box_1: 4-D tensor [cell_size, cell_size, boxes_per_cell, 4] ===> [x_center, y_center, width, height]
            box_2: 4-D tensor [cell_size, cell_size, boxes_per_cell, 4] ===> [x_center, y_center, width, height]
        Return: 
            iou: 3-D tensor [cell_size, cell_size, boxes_per_cell]
        """
        with tf.variable_scope(scope):
            """

            """
            boxes1 = tf.stack([boxes1[:, :, :, :, 0] - boxes1[:, :, :, :, 2] / 2.0,
                               boxes1[:, :, :, :, 1] - boxes1[:, :, :, :, 3] / 2.0,
                               boxes1[:, :, :, :, 0] + boxes1[:, :, :, :, 2] / 2.0,
                               boxes1[:, :, :, :, 1] + boxes1[:, :, :, :, 3] / 2.0])
            boxes1 = tf.transpose(boxes1, [1, 2, 3, 4, 0])

            boxes2 = tf.stack([boxes2[:, :, :, :, 0] - boxes2[:, :, :, :, 2] / 2.0,
                               boxes2[:, :, :, :, 1] - boxes2[:, :, :, :, 3] / 2.0,
                               boxes2[:, :, :, :, 0] + boxes2[:, :, :, :, 2] / 2.0,
                               boxes2[:, :, :, :, 1] + boxes2[:, :, :, :, 3] / 2.0])
            boxes2 = tf.transpose(boxes2, [1, 2, 3, 4, 0])


    def loss_layer(self, predicts, labels, scope='Loss_layer'):
        """
        Args:
            predict tensor: [batch_size, cell_size, cell_size, 18 + num_class] 18 is 9-points'-coord
                             last dimension: coord(18) ==> classes(num_class)
            labels tensor:  [batch_size, cell_size, cell_size, 20 + num_class] 20 is 9-points'-coord + 1-response + 1-confidence
                             last dimension: response(1) ==> coord(18) ==> classes(num_class) ==> confidence(1)
        """
        self.predict_coord = tf.reshape(predicts[:, :, :, : self.boundry_1], [self.Batch_Size, self.cell_size, self.cell_size, self.num_coord])
        self.predict_classes = tf.reshape(predicts[:, :, :, self.boundry_1:], [self.Batch_Size, self.cell_size, self.cell_size, self.num_class])

        self.response = tf.reshape(labels[:, :, :, 0], [self.Batch_Size, self.cell_size, self.cell_size, 1])
        self.labels_coord = tf.reshape(labels[:, :, :, 1:self.boundry_1+1], [self.Batch_Size, self.cell_size, self.cell_size, self.num_coord])
        self.labels_classes = tf.reshape(labels[:, :, :, self.boundry_1+1:-1], [self.Batch_Size, self.cell_size, self.cell_size, self.num_class])
        self.labels_conf = tf.reshape(labels[:, :, :, -1], [self.Batch_Size, self.cell_size, self.cell_size, 1])

        self.off_set = tf.constant(self.off_set, dtype=tf.float32)
        self.off_set = tf.reshape(self.off_set, [1, self.cell_size, self.cell_size, self.boxes_per_cell])
        self.off_set = tf.tile(self.off_set, [self.Batch_Size, 1, 1, 1])   
        ## off_set shape : [self.Batch_Size, self.cell_size, self.cell_size, self.boxes_per_cell]

        predict_boxes_tran = tf.stack([(self.predict_coord)])
        #self.dt_x = dist(self.predict_coord, self.labels_coord)
        #self.predict_conf = confidence_func(self.dt_x)

        ## coord loss


        return loss