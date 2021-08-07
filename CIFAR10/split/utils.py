import torch
import torch.nn.functional as F


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
    * Input: (1, channel=1, nof_feautre)
    * Return: padded Input: (1, 1, pad[0]+ nof_feautre + pad[1])
    '''
    output = torch.cat([Input[:, :, -pad[0]:], Input,
                        Input[:, :, :pad[1]]], dim=2) if pad[0] > 0 else torch.cat([Input,
                                                                                    Input[:, :, :pad[1]]], dim=2)
    return output


def circular_conv(W, Key=None):
    '''
    * Return: (Key, K*W) or K*W if K is not None
    * V:(Batch, nof_feature) (no compression)
    * V = Key * W, where * denotes circular convolution
    * The keys are generated by random normal distribution with mean 0 and variance 1/d
    * With unit norm
    * Key:(Batch size, nof_feature)->(1, 1, Batch size, nof_feature)
    * W:(Batch size, nof_feature)->(Batch size, 1, 1, nof_feature)
    '''
    return_key = False
    if Key is None:
        # Generate the key
        mean = 0
        dim = 1
        for i in range(1, len(W.shape)):
            dim *= W.shape[i]
        std = (1/dim) ** (1/2)
        Key = (torch.randn(W.shape)*std + mean).cuda()
        Key /= torch.norm(Key, dim=1, keepdim=True)
        Key = Key.reshape([1, 1, Key.shape[0], -1])
        return_key = True

    # Circular convolution by circular padding
    # Circular padding: [1,2,3] with pad(2,0) -> [2,3] +[1,2,3] + []
    W = W.reshape([W.shape[0], 1, 1, -1])

    # W = [w1 w2 w0 w1 w2] Key = [K2 K1 K0] (flipped)
    # faster than flip() when dim is large
    inverse_idx = torch.arange(Key.shape[3]-1, -1, -1)
    pad_W = circular_pad2d(W, pad=(W.shape[-1]-1, 0))
    V = torch.cat([F.conv1d(
        pad_W[i],
        Key[:, :, i, inverse_idx],
        padding=0, stride=1).reshape([1, -1]) for i in range(len(pad_W))])
    return (Key, V) if return_key else V


def circular_corr(V, Key):
    ''' Circular Correlation
    * Return: KoV (Batch, nof_feature)
    * W = Key o V = Key o (Key*W), where o denotes circular convolution
    * Key:(1, 1, Batch, nof_feature)
    * V:(Batch, nof_feature)->(Batch, 1, 1, nof_feature)
    * W:(Batch, nof_feature)
    '''
    # Circular pad compressV -> [v0 v1 v2] -> [v0 v1 v2 v0 v1]
    # Key = [k0 k1 k2]
    V = V.reshape([V.shape[0], 1, 1, -1])

    pad_V = circular_pad2d(
        V, pad=(0, V.shape[-1]-1))
    W = torch.cat([F.conv1d(
        pad_V[i],
        Key[:, :, i, :],
        padding=0, stride=1).reshape([1, -1])
        for i in range(len(pad_V))])
    return W
