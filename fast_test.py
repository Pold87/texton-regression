import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import math
import scipy
import cv2
from matplotlib.cbook import get_sample_data
import matplotlib.image as mpimg
from matplotlib.offsetbox import TextArea, DrawingArea, OffsetImage, \
    AnnotationBbox
from matplotlib._png import read_png
import argparse
from multiprocessing import Process, Value
from sklearn.externals import joblib
from filterpy.kalman import KalmanFilter
from filterpy.common import Q_discrete_white_noise
from scipy.linalg import block_diag

import thread
import time
import threading
from treXton import img_to_texton_histogram, RGB2Opponent, imread_opponent
from treXtonConfig import parser

args = parser.parse_args()
mymap = args.mymap

def mydist(x,y):
    if x[0] == y[0]:
        return 0
    else:
        return 1


def pred_ints(model, X, percentile=95):
    err_down = []
    err_up = []
    preds = []
    for pred in model.estimators_:
        preds.append(pred.predict(X)[0])
    err_down = np.percentile(preds, (100 - percentile) / 2. )
    err_up = np.percentile(preds, 100 - (100 - percentile) / 2.)
    return err_down, err_up

def init_tracker():
    tracker = KalmanFilter(dim_x=4, dim_z=2)
    dt = 1.0   # time step

    tracker.F = np.array([[1, dt, 0,  0],
                          [0,  1, 0,  0],
                          [0,  0, 1, dt],
                          [0,  0, 0,  1]])

    tracker.H = np.array([[1, 0, 0, 0],
                          [0, 0, 1, 0]])

    tracker.R = np.eye(2) * 1000
    q = Q_discrete_white_noise(dim=2, dt=dt, var=1)
    tracker.Q = block_diag(q, q)
    tracker.x = np.array([[2000, 0, 700, 0]]).T
    tracker.P = np.eye(4) * 50.
    return tracker


def rotate_coordinates(xs, ys, theta):

    """
    This function rotates 2D coordinates by a specified angle.
    """
    
    xs_new = np.zeros(len(xs))
    ys_new = np.zeros(len(ys))
    
    for i, (x, y) in enumerate(zip(xs, ys)):

        new_x = np.cos(theta) * x - np.sin(theta) * y
        new_y = np.sin(theta) * x + np.cos(theta) * y

        xs_new[i] = new_x
        ys_new[i] = new_y

    return xs_new, ys_new

def main():


    # Load k-means

    kmeans = []
    for channel in range(3):
    
        kmean = joblib.load('classifiers/kmeans' + str(channel) + '.pkl')
        kmeans.append(kmean)
        
    # Load random forest
    if args.do_separate:
        clf_x = joblib.load('classifiers/clf_x.pkl')
        clf_y = joblib.load('classifiers/clf_y.pkl') 
    
    else:
        clf0 = joblib.load('classifiers/clf0.pkl')
        clf1 = joblib.load('classifiers/clf1.pkl')
        clfs = [clf0, clf1]

    # Load tfidf
    tfidf = joblib.load('classifiers/tfidf.pkl') 
        
    path = args.test_imgs_path
    labels = pd.read_csv("../orthomap/imgs/sift_targets.csv", index_col=0)

    if args.standardize:
        mean, stdv = np.load("mean_stdv.npy")

    if args.filter:
        my_filter = init_tracker()

    test_on_the_fly = True
    if test_on_the_fly:
        xs = []
        ys = []


        
    errors = []
    errors_x = []
    errors_y = []

    for i in labels.index:

        img_path = path + str(i) + ".png"
        pic = imread_opponent(img_path)


        if args.color_standardize:

            mymean = np.mean(np.ravel(pic[:, :, 0]))
            mystdv = np.std(np.ravel(pic[:, :, 0]))


            pic[:, :, 0] = pic[:, :, 0] - mymean
            pic[:, :, 0] = pic[:, :, 0] / mystdv
            pic[:, :, 1] = pic[:, :, 1] / mystdv
            pic[:, :, 2] = pic[:, :, 2] / mystdv


        if args.local_standardize:
            for channel in range(args.channels):

                mymean = np.mean(np.ravel(pic[:, :, channel]))
                mystdv = np.std(np.ravel(pic[:, :, channel]))

                pic[:, :, channel] = pic[:, :, channel] - mymean
                pic[:, :, channel] = pic[:, :, channel] / mystdv

            
        if args.standardize:
            for channel in range(args.channels):
                mean, stdv = np.load("mean_stdv_" + str(channel) + ".npy")
                pic[:, :, channel] = pic[:, :, channel] - mean
                pic[:, :, channel] = pic[:, :, channel] / stdv
            

        # Get texton histogram of picture
        query_histograms = []

                
        for channel in range(args.channels):
            histogram = img_to_texton_histogram(pic[:, :, channel],
                                                    kmeans[channel],
                                                    args.max_textons,
                                                    args.num_textons,
                                                    1,
                                                    args,
                                                    channel)
            query_histograms.append(histogram)
                             
        histogram = np.ravel(query_histograms)             
             

        if args.tfidf:
            histogram = tfidf.transform(histogram.reshape(1, -1)).todense()
            histogram = np.ravel(histogram)

        
        preds = []
        if args.do_separate:
            pred_x = clf_x.predict(histogram.reshape(1, -1))
            pred_y = clf_y.predict(histogram.reshape(1, -1))
            pred  = np.array([(pred_x[0], pred_y[0])])
            #err_down, err_up = pred_ints(clf_x, [histogram], percentile=75)
            #print(err_down)
            #print(pred[0][0])
            #print(err_up)
            #print("")
            
        else:
            for i, clf in enumerate(clfs):
                print(i)
                pred = clf.predict(histogram.reshape(1, -1))
                err_down, err_up = pred_ints(clf, histogram.reshape(1, -1), percentile=90)
                print(err_down)
                print(err_up)
                print("")
                preds.append(pred)

            pred = np.mean(preds, axis=0)

#        if args.filter:
#            my_filter.update(pred.T)
#            filtered_pred = (my_filter.x[0][0], my_filter.x[2][0])
#            my_filter.predict()


        #print("Ground truth (x, y)", xs_opti[i], ys_opti[i])
        #print("Prediction (x, y)", pred[0][0], pred[0][1])

        if test_on_the_fly:
            if args.do_separate:
                xy = (pred_x[0], pred_y[0])
            else:
                xy = (pred[0][0], pred[0][1])

        else:
            xy = (xs[i], ys[i])


        ground_truth =  (labels.x[i], labels.y[i])
        diff =  np.subtract(ground_truth, xy)
        abs_diff = np.fabs(diff)
        errors_x.append(abs_diff[0])
        errors_y.append(abs_diff[1])
        error = np.linalg.norm(abs_diff)
        errors.append(error)
                
          
    print("errors", np.mean(errors))
    print("errors x", np.mean(errors_x))
    print("errors y", np.mean(errors_y))
         

        

if __name__ == "__main__":
    main()
