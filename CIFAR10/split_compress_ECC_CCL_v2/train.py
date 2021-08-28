import sys
import time
import torch
import numpy as np
import matplotlib.pyplot as plt
import os
import torchvision.models
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from PIL import Image
import torchvision.transforms as transforms
from argparse import ArgumentParser

from utils import CC_Loss
from model import SplitAlexNet
from torchvision.transforms.transforms import Lambda

''' 
* Reference https://bExponential Lambda Log.openmined.org/split-neural-networks-on-pysyft/
* Corresponding experiments: Training with different batch size
'''
Dir = os.path.dirname(__file__)
train_dir = os.path.join(Dir, '..', 'CIFAR', 'train')
test_dir = os.path.join(Dir, '..', 'CIFAR', 'test')

''' 
* Load the data from .npy
'''
train_image = np.load(os.path.join(train_dir, 'train_images.npy'))
train_labels = np.load(os.path.join(train_dir, 'train_labels.npy'))
test_image = np.load(os.path.join(test_dir, 'test_images.npy'))
test_labels = np.load(os.path.join(test_dir, 'test_labels.npy'))

print("Size of training images:{}".format(train_image.shape))
print("Size of training labels:{}".format(train_labels.shape))
print("Size of testing images:{}".format(test_image.shape))
print("Size of testing labels:{}".format(test_labels.shape))

''' 
* Argument Parser
'''
parser = ArgumentParser()
parser.add_argument("--batch", required=False, type=int,
                    default=32, help="The batch size")
parser.add_argument("--epoch", required=False, type=int,
                    default=30, help="The batch size")
parser.add_argument("--Lambda", required=False, type=float,
                    default=0.0001, help="The batch size")
parser.add_argument("--dump_path", required=False, type=str,
                    default='./logs', help="The directory to save logs and models")
parser.add_argument("--restore", required=False,
                    action="store_true", help="Whether or not to restore model status from the pickle files in dump_path")
args = parser.parse_args()

# Create directory for dump path
saved_path = os.path.join(
    os.path.dirname(__file__), args.dump_path)
if not os.path.isdir(saved_path):
    os.makedirs(saved_path)
''' 
********************************************
* Data Augmentation and Dataset, DataLoader
********************************************
'''
train_transform = transforms.Compose([
    transforms.ToPILImage(),
    # transforms.Resize([128, 128]),
    transforms.ToTensor(),
])

test_transform = transforms.Compose([
    transforms.ToPILImage(),
    # transforms.Resize([128, 128]),
    transforms.ToTensor(),
])


class ImageDataset(Dataset):
    def __init__(self, x, y, transform):
        '''
        * x: training data
        * y: training label
        * transform: transforms that will be operated on images
        '''
        self.x = x
        self.y = torch.LongTensor(y)
        self.transform = transform

    def __len__(self):
        return len(self.x)

    def __getitem__(self, index):
        '''
        * The Data loader will create integers which indicates indices
        * And the Dataset should return the samples which mapped by these indices
        '''
        X = self.x[index]
        Y = self.y[index]

        # Transform X into tensor( Y is already long tensor)
        X = self.transform(X)
        return X, Y


batch_size = args.batch

Train_Dataset = ImageDataset(train_image, train_labels, train_transform)
Test_Dataset = ImageDataset(test_image, test_labels, test_transform)
Train_Loader = DataLoader(Train_Dataset, batch_size=batch_size, shuffle=True)
Test_Loader = DataLoader(Test_Dataset, batch_size=batch_size, shuffle=False)

''' 
* Model Architecture: Alexnet
'''

start_epoch = 1
learning_rate = 1e-4
Lambdas = [args.Lambda for i in range(args.epoch+1)]
num_epoch = args.epoch

model = SplitAlexNet()

# Restore the model status from pickle
if args.restore:
    last_dict = torch.load(os.path.join(
        saved_path, "Alexnet.pth"))
    start_epoch = last_dict["Epoch"]
    model = last_dict["Model"]

# add model into tensorborad
model.cuda()
CE_Loss = nn.CrossEntropyLoss()

# Check the architecture of Alexnet
print("{:=^40}".format("Architecture"))
print(model.models[0])
print(model.models[1])
print("{:=^40}".format("End"))

best_acc = 0.
best_loss = float("inf")
train_acc_list = []
train_CE_loss_list = []
train_CCL_loss_list = []
train_grad_rec_loss_list = []
test_acc_list = []
test_CE_loss_list = []
test_rec_loss_list = []

for epoch in range(start_epoch, num_epoch+1):
    ''' Training part'''
    Lambda = Lambdas[epoch]
    model.train()
    train_CE_loss = 0.
    train_CCL_loss = 0.
    train_grad_rec_loss = 0.
    train_acc = 0.
    test_CE_loss = 0.
    test_rec_loss = 0.
    test_acc = 0.
    epoch_start_time = time.time()
    for i, (train_x, train_y) in enumerate(Train_Loader, 1):
        print("Batch [{}/{}]".format(i, len(Train_Loader)), end='\r')
        train_x = train_x.cuda()
        train_y = train_y.cuda()

        # y_pred: (batch size, 10)
        y_pred = model(train_x)

        # Compute the loss
        batch_L_CE = CE_Loss(y_pred, train_y)
        batch_L_CCL = CC_Loss(model.front[0], model.front[1])

        # Clean the gradient
        model.zero_grad()

        # Compute the gradient
        batch_L_grad_rec = model.backward(
            batch_L_CE, batch_L_CCL, Lambda)

        # Update the model
        model.step()

        train_CE_loss += len(train_x) * (batch_L_CE).item()
        train_CCL_loss += len(train_x) * (batch_L_CCL).item()
        train_grad_rec_loss += len(train_x) * batch_L_grad_rec.item()
        train_acc += np.sum(np.argmax(y_pred.detach().cpu().numpy(),
                                      axis=1) == train_y.cpu().numpy())
    train_CE_loss /= Train_Dataset.__len__()
    train_CCL_loss /= Train_Dataset.__len__()
    train_grad_rec_loss /= Train_Dataset.__len__()
    train_acc /= Train_Dataset.__len__()

    # Testing part
    model.eval()
    with torch.no_grad():
        for test_x, test_y in Test_Loader:
            test_x = test_x.cuda()
            test_y = test_y.cuda()

            y_pred = model(test_x)

            # Compute the loss and acc
            test_CE_loss += CE_Loss(y_pred, test_y).item() * len(test_x)
            test_rec_loss += torch.mean(
                (model.front[1]-model.front[0])**2).item() * len(test_x)
            test_acc += np.sum(np.argmax(y_pred.detach().cpu().numpy(),
                                         axis=1) == test_y.cpu().numpy())
    test_CE_loss /= len(Test_Dataset)
    test_rec_loss /= len(Test_Dataset)
    test_acc /= len(Test_Dataset)
    # Output the result
    print("Epoch [{}/{}] Time:{:.3f} secs Train_acc:{:.4f} train_CE_loss:{:.4f} train_CCL_loss:{:.4f}".format(epoch, num_epoch, time.time()-epoch_start_time,
                                                                                                              train_acc, train_CE_loss, train_CCL_loss))
    print("Test_acc:{:.4f} test_CE_loss:{:.4f} test_rce_loss:{:.4f}".format(
        test_acc, test_CE_loss, test_rec_loss))

    # Append the accuracy and loss to list
    train_acc_list.append(train_acc)
    train_CE_loss_list.append(train_CE_loss)
    train_CCL_loss_list.append(train_CCL_loss)
    train_grad_rec_loss_list.append(train_grad_rec_loss)
    test_acc_list.append(test_acc)
    test_CE_loss_list.append(test_CE_loss)
    test_rec_loss_list.append(test_rec_loss)

    ''' Save the best model '''
    if test_acc > best_acc:
        best_acc = test_acc
        best_loss = test_CE_loss
        print("Save model with Test_acc:{:.4f} test_CE_loss:{:.4f} at {}".format(
            best_acc, best_loss, os.path.join(
                saved_path, "Alexnet.pth")))
        saved_dict = {
            "Epoch": epoch+1,
            "Model": model
        }
        torch.save(saved_dict, os.path.join(
            saved_path, "Alexnet.pth"))


# Record the train acc and train loss
with open(os.path.join(saved_path, "train_accuracy_{}_{}.csv".format(args.batch, args.Lambda)), "w") as f:
    for i in range(len(train_acc_list)-1):
        f.write(str(train_acc_list[i])+",")
    f.write(str(train_acc_list[-1]))
with open(os.path.join(saved_path, "train_CE_loss_{}_{}.csv".format(args.batch, args.Lambda)), "w") as f:
    for i in range(len(train_CE_loss_list)-1):
        f.write(str(train_CE_loss_list[i])+",")
    f.write(str(train_CE_loss_list[-1]))

with open(os.path.join(saved_path, "train_CCL_loss_{}_{}.csv".format(args.batch, args.Lambda)), "w") as f:
    for i in range(len(train_CCL_loss_list)-1):
        f.write(str(train_CCL_loss_list[i])+",")
    f.write(str(train_CCL_loss_list[-1]))
with open(os.path.join(saved_path, "train_grad_rec_loss_{}_{}.csv".format(args.batch, args.Lambda)), "w") as f:
    for i in range(len(train_grad_rec_loss_list)-1):
        f.write(str(train_grad_rec_loss_list[i])+",")
    f.write(str(train_grad_rec_loss_list[-1]))

# Record the validation accuracy and validation loss
with open(os.path.join(saved_path, "test_accuracy_{}_{}.csv".format(args.batch, args.Lambda)), "w") as f:
    for i in range(len(test_acc_list)-1):
        f.write(str(test_acc_list[i])+",")
    f.write(str(test_acc_list[-1]))

with open(os.path.join(saved_path, "test_CE_loss_{}_{}.csv".format(args.batch, args.Lambda)), "w") as f:
    for i in range(len(test_CE_loss_list)-1):
        f.write(str(test_CE_loss_list[i])+",")
    f.write(str(test_CE_loss_list[-1]))
with open(os.path.join(saved_path, "test_rec_loss_{}_{}.csv".format(args.batch, args.Lambda)), "w") as f:
    for i in range(len(test_rec_loss_list)-1):
        f.write(str(test_rec_loss_list[i])+",")
    f.write(str(test_rec_loss_list[-1]))
