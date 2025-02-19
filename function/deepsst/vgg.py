import torch.nn as nn
import torch.nn.functional as F

__all__ = ["vgg11", "vgg13", "vgg16", "vgg19"]

cfg = {
    "A": [64, "M", 128, "M", 256, 256, "M", 512, 512, "M", 512, 512, "M"],
    "B": [64, 64, "M", 128, 128, "M", 256, 256, "M", 512, 512, "M", 512, 512, "M"],
    "D": [
        64,
        64,
        "M",
        128,
        128,
        "M",
        256,
        256,
        256,
        "M",
        512,
        512,
        512,
        "M",
        512,
        512,
        512,
        "M",
    ],
    "E": [
        64,
        64,
        "M",
        128,
        128,
        "M",
        256,
        256,
        256,
        256,
        "M",
        512,
        512,
        512,
        512,
        "M",
        512,
        512,
        512,
        512,
        "M",
    ],
}


class VGG(nn.Module):
    def __init__(self, features, num_classes=10, softmax=True):
        super(VGG, self).__init__()
        self.softmax = softmax
        self.features = features
        self.flatten = nn.Flatten()
        self.classifier = nn.Linear(512, num_classes)
        self._initialize_weights()

    def forward(self, x):
        x = self.features(x)
        x = self.flatten(x)
        x = self.classifier(x)
        if self.softmax:
            x = F.softmax(x,dim=1)
        return x

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight.data)
                if m.bias is not None:
                    m.bias.data.zero_()
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
            elif isinstance(m, nn.Linear):
                m.weight.data.normal_(0, 0.01)
                m.bias.data.zero_()


def make_layers(cfg, batch_norm=False):
    layers = []
    in_channels = 3
    for v in cfg:
        if v == "M":
            layers += [nn.MaxPool2d(kernel_size=2, stride=2)]
        else:
            conv2d = nn.Conv2d(in_channels, v, kernel_size=3, padding=1)
            if batch_norm:
                layers += [conv2d, nn.BatchNorm2d(v), nn.ReLU(inplace=True)]
            else:
                layers += [conv2d, nn.ReLU(inplace=True)]
            in_channels = v
    return nn.Sequential(*layers)


def vgg11(num_classes,softmax):
    return VGG(make_layers(cfg["A"], batch_norm=True), num_classes,softmax)


def vgg13(num_classes,softmax):
    return VGG(make_layers(cfg["B"], batch_norm=True), num_classes,softmax)


def vgg16(num_classes,softmax):
    return VGG(make_layers(cfg["D"], batch_norm=True), num_classes,softmax)


def vgg19(num_classes,softmax):
    return VGG(make_layers(cfg["E"], batch_norm=True), num_classes,softmax)