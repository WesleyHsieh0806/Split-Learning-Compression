import torch
import torch.nn.functional as F
from math import sqrt


def MSE_ReLu_Loss(z, recover_z):
    '''
    * Input: z and recover_z (N, nof_feature)
    * Since z will be sent to relu in the next layer, now we will just compute the MSE between relu(z)
    '''
    z = F.relu(z)
    recover_z = F.relu(recover_z)
    return torch.mean((z-recover_z)**2)


def normalize_for_circular(W):
    '''
    * W: shape(Batch, nof_feature)
    * Normalize input tensor to N(0, 1/d)
    '''
    # Normalize W to N(0, 1/d)
    std, mean = torch.std_mean(W, dim=1, keepdim=True)
    W = W - mean
    W = W/(sqrt(W.shape[-1])*std)
    return W, std, mean


def CC_Loss(z, recover_z):
    '''
    * Feature Cross-Correlation Loss
    * Input:
    *   @ z:         tensor of shape(B, feature dim)
    *   @ recover_z: tensor of shape(B, feature dim)
    * Goal: To ensure the feature cross-correlation is similar between z and recover_z
    '''
    # Normalize along the batch dimension
    z = (z - z.mean(0))
    norm_z = z / torch.norm(z, dim=0, keepdim=True)  # (B, dim)
    CC_norm_z = torch.mm(norm_z.T, norm_z)

    recover_z = recover_z - recover_z.mean(0)
    norm_recover_z = recover_z / \
        torch.norm(recover_z, dim=0, keepdim=True)  # (B, dim)
    CC_norm_recover_z = torch.mm(norm_recover_z.T, norm_recover_z)

    return torch.mean((CC_norm_z-CC_norm_recover_z)**2)


def circular_pad2d(Input, pad: tuple):
    '''
    * Input: (1, channel=1, batch, nof_feautre)
    * Return: padded Input: (1, 1, batch, pad[0]+ nof_feautre + pad[1])
    '''
    output = torch.cat([Input[:, :, :, -pad[0]:], Input,
                        Input[:, :, :, :pad[1]]], dim=3) if pad[0] > 0 else torch.cat([Input,
                                                                                       Input[:, :, :, :pad[1]]], dim=3)
    return output


def circular_pad1d(Input, pad: tuple):
    '''
    * Input: (1, channel=1, batch, nof_feautre)
    * Return: padded Input: (1, 1, batch, pad[0]+ nof_feautre + pad[1])
    '''
    output = torch.cat([Input[:, :, -pad[0]:], Input,
                        Input[:, :, :pad[1]]], dim=2) if pad[0] > 0 else torch.cat([Input,
                                                                                    Input[:, :, :pad[1]]], dim=2)
    return output


def circular_conv(W, Key):
    '''
    * Return: (Key, K*W) or K*W if K is not None
    * V:(1, nof_feature) (alread compressed)
    * V = Key * W, where * denotes circular convolution
    * The keys are generated by random normal distribution with mean 0 and variance 1/d
    * With unit norm
    * Key:(1, 1, Batch size, nof_feature)
    * W:(Batch size, nof_feature)->(1, 1, Batch size, nof_feature)
    '''

    # Circular convolution by circular padding
    # Circular padding: [1,2,3] with pad(2,0) -> [2,3] +[1,2,3] + []
    W = W.reshape([1, 1, W.shape[0], -1])

    # W = [w1 w2 w0 w1 w2] Key = [K2 K1 K0] (flipped)
    # faster than flip() when dim is large
    inverse_idx = torch.arange(Key.shape[3]-1, -1, -1)
    V = F.conv2d(
        circular_pad2d(W, pad=(W.shape[-1]-1, 0)),
        Key[:, :, :, inverse_idx],
        padding=0, stride=1).reshape([1, -1])
    return V


def circular_corr(compress_V, Key):
    ''' Circular Correlation
    * Return: KoV (Batch, nof_feature)
    * W = Key o V = Key o (Key*W), where o denotes circular convolution
    * Key:(1, 1, Batch, nof_feature) -> (Batch, 1, nof_feature)
    * compress_V:(1, nof_feature)->(1, 1, nof_feature)
    * W:(1, Batch, nof_feature) -> (Batch, nof_feature)
    '''
    # Circular pad compressV -> [v0 v1 v2] -> [v0 v1 v2 v0 v1]
    # Key = [k0 k1 k2]
    compress_V = compress_V.unsqueeze(dim=0)

    Key = Key.reshape([Key.shape[2], 1, -1])
    W = F.conv1d(circular_pad1d(
        compress_V, pad=(0, compress_V.shape[-1]-1)), Key, stride=1)
    return W.reshape([W.shape[1], -1])
