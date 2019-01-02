# -*- coding: utf-8 -*-
# ---------------------
# Get the training & testing datasets and set the labels
# @Author: Fan, Mo
# @Email: fmo@nullmax.ai
# ---------------------

import os
import random
from multiprocessing import Process, Queue

import numpy as np
import tensorflow as tf

import yolo.config as cfg


class ImageNet(object):
    def __init__(self, pre=False):
        self.pre = pre
        self.epoch = 1
        self.max_num = 1000
        self.tfrecords_file_num = 1
        self.next_images = None
        self.next_labels = None
        self.train_init_op = None
        self.trainrecords = None
        self.testrecords = None
        self.total_file_num = 0
        self.each_process_file_num = 0
        self.imageCropHeight = 416
        self.imageCropWidth = 416
        self.imageDepth = 3

        if pre:
            self.preprocess_data()


    def preprocess_data(self):
        # generate 3 .csv files (imagenet_train.csv, imagenet_test.csv, imagenet_valid.csv)
        self.makecsv()

        # generate .tfrecord files (train_'record_num'.tfrecord, test_'record_num'.tfrecord, valid_'record_num'.tfrecord)
        phases = ['train', 'test', 'valid']
        for phase in phases:
            # transfer data
            with open('imagenet_{}.csv'.format(phase), 'r') as openfile:
                self.openrecords = openfile.readlines()
            self.total_file_num = len(self.openrecords)
            # for 4 cpus, each process 1 lsit
            self.each_process_file_num = int(self.total_file_num / 4.0)
            list1 = self.openrecords[:self.each_process_file_num]
            lsit2 = self.openrecords[self.each_process_file_num:2*self.each_process_file_num]
            list3 = self.openrecords[2*self.each_process_file_num:3*self.each_process_file_num]
            list4 = self.openrecords[3*self.each_process_file_num:]
            # create 4 queues, 4 sub processes
            # p1-4 generate a .tfrecord file
            q1 = Queue()
            q2 = Queue()
            q3 = Queue()
            q4 = Queue()
            p1 = Process(target=self.gen_tfrecord, args=(list1, q1, phase, ))
            p2 = Process(target=self.gen_tfrecord, args=(lsit2, q2, phase, ))
            p3 = Process(target=self.gen_tfrecord, args=(list3, q3, phase, ))
            p4 = Process(target=self.gen_tfrecord, args=(list4, q4, phase, ))
            p_list = [p1, p2, p3, p4]
            _ = map(Process.start, p_list)
        
            #父进程循环查询队列的消息，并且每10秒更新一次
            #progress_str = 'PID:%i Processing:%i/%i | PID:%i Processing:%i/%i | PID:%i Processing:%i/%i | PID:%i Processing:%i/%i \r'
            #while(True):
            #    try:
            #        msg1 = q1.get()
            #        msg2 = q2.get()
            #        msg3 = q3.get()
            #        msg4 = q4.get()
            #        print(progress_str % (msg1[0],msg1[1],len(list1),msg2[0],msg2[1],len(list2),msg3[0],msg3[1],len(list3),msg4[0],msg4[1],len(list4)))
            #        time.sleep(10)
            #    except:
            #        break

    def gen_tfrecord(self, records, queue, phase):
        """
        Generate TFRECORD files
        Args:
            records: A list, each element is image folder name + class name
            queue: queue name, communicate with parent queue
        """
        tfrecords_file_num = self.tfrecords_file_num
        file_num = 0
        total_num = len(records)
        writer = tf.python_io.TFRecordWriter("data/datasets/imagenet/tfdata/{}/".format(phase) + str(os.getpid()) + "_" + str(tfrecords_file_num) + ".tfrecord")
        pid = os.getpid()
 
        for record in records:
            file_num += 1
            fields = record.strip('\n').split(',')
            with open(fields[0], 'rb') as jpgfile:
                img = jpgfile.read()
            label = np.array(int(fields[1]))
            ex = self.make_example(img, label)
            writer.write(ex.SerializeToString())
            #send messege to parent process after every 100 records made
            if file_num % 100 == 0:
                queue.put((pid, file_num))
            if file_num % self.max_num == 0 and file_num < total_num:
                writer.close()
                tfrecords_file_num += 1
                writer = tf.python_io.TFRecordWriter("data/datasets/imagenet/tfdata/{}/".format(phase) + str(os.getpid()) + "_"+str(tfrecords_file_num) + ".tfrecord")
        writer.close()


    def next_batches(self):
        """
        Get images and labels (tfrecord) for trianing
        """
        with tf.device('/cpu:0'):
            train_files_names = os.listdir('data/datasets/imagenet/tfdata/train/')
            train_files = ['data/datasets/imagenet/tfdata/train/'+ item for item in train_files_names]
            dataset_train = tf.data.TFRecordDataset(train_files)
            dataset_train = dataset_train.map(self._parse_function, num_parallel_calls=4)
            dataset_train = dataset_train.repeat(10)
            dataset_train = dataset_train.batch(cfg.BATCH_SIZE)
            dataset_train = dataset_train.prefetch(cfg.BATCH_SIZE)
            iterator = tf.data.Iterator.from_structure(dataset_train.output_types, dataset_train.output_shapes)
            self.next_images, self.next_labels = iterator.get_next()
            self.epoch += 1
            self.train_init_op = iterator.make_initializer(dataset_train)
        return self.next_images, self.next_labels


    def next_batches_test(self):
        """
        Get images and labels (tfrecord) for testing
        """
        with tf.device('/cpu:0'):
            test_files_names = os.listdir('data/datasets/imagenet/tfdata/test/')
            test_files = ['data/datasets/imagenet/tfdata/test/' + item for item in test_files_names]
            datasets_test = tf.data.TFRecordDataset(test_files)
            datasets_test = datasets_test.map(self._parse_function, num_parallel_calls=4)
            datasets_test = datasets_test.repeat(10)
            datasets_test = datasets_test.batch(cfg.BATCH_SIZE)
            datasets_test = datasets_test.prefetch(cfg.BATCH_SIZE)
            iterator = tf.data.Iterator.from_structure(datasets_test.output_types, datasets_test.output_shapes)
            self.next_images, self.next_labels = iterator.get_next()
            self.epoch += 1
            self.train_init_op = iterator.make_initializer(datasets_test)
        return self.next_images, self.next_labels

        
    def makecsv(self):
        """
        Make 3 csv files (train, valid, test) for later use
        """
        classes = os.listdir('data/datasets/imagenet/')  # imagenet stored in data/datasets/imagenet/
        label_dict = {} # key is name, value is 0 - 999
        for i in range(len(classes)):
            label_dict[classes[i]] = i

        image_labels_list = [] # each element is folder name + class name
        for i in range(len(classes)):
            path = 'data/datasets/imagenet/' + classes[i] + '/'
            images_files = os.listdir(path)
            label = str(label_dict[classes[i]])
            for image_file in images_files:
                image_labels_list.append(path + image_file + ',' + label + '\n')

        random.shuffle(image_labels_list)
        num = len(image_labels_list)
        with open('imagenet_train.csv', 'w') as file:
            file.writelines(image_labels_list[:int(num * 0.8)])
        with open('imagenet_test.csv', 'w') as file:
            file.writelines(image_labels_list[int(num * 0.9):])
        with open('imagenet_valid.csv', 'w') as file:
            file.writelines(image_labels_list[int(num * 0.8):int(num * 0.9)])


    def make_example(self, image, label):
        """
        Transfer images data and labels data into TFRECORD format
        """
        return tf.train.Example(features=tf.train.Features(feature={
            'image' : tf.train.Feature(bytes_list=tf.train.BytesList(value=[image])),
            'label' : tf.train.Feature(int64_lsit=tf.train.Int64List(Value=[label]))
        }))


    def _parse_function(self, filename, label):
        """
        A map function, to deal with each data in Datasets
        """
        image_string = tf.read_file(filename)
        image_decoded = tf.image.decode_jpeg(image_string, channels=3)
        image_height = tf.shape(image_decoded)[0]
        image_width = tf.shape(image_decoded)[1]
        
        # generate random value between 256-481 ()
        random_s = tf.random_uniform([1], minval=256, maxval=481, dtype=tf.int32)[0]
        # if height < width: (random_s, random_s/height*width)
        # if height > width: (random_s/width*height, random_s)
        resized_height, resized_width = tf.cond(image_height < image_width, 
                    lambda: (random_s, tf.cast(tf.multiply(tf.cast(image_width, tf.float64), tf.divide(random_s, image_height)), tf.int32)), 
                    lambda: (tf.cast(tf.multiply(tf.cast(image_height, tf.float64),tf.divide(random_s, image_width)), tf.int32), random_s))

        image_float = tf.image.convert_image_dtype(image_decoded, tf.float32)
        image_resized = tf.image.resize_images(image_float, [resized_height, resized_width])
        image_flipped = tf.image.random_flip_left_right(image_resized)
        # random crop the image to 416 X 416
        image_cropped = tf.random_crop(image_flipped, [self.imageCropHeight, self.imageCropWidth, self.imageDepth])
        image_distorted = tf.image.random_brightness(image_cropped, max_delta=63)
        image_distorted = tf.image.random_contrast(image_distorted, lower=0.2, upper=1.8)
        # uniform the image by (value - mean) / variance
        image_distorted = tf.image.per_image_standardization(image_distorted)
        #image_distorted = tf.transpose(image_distorted, perm=[2, 0, 1])
        return image_distorted, label