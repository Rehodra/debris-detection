"""Pure-PyTorch ResNet18 with official ImageNet weights (no torchvision dependency).

torchvision's native ops fail to load on this Windows setup, so we define the standard
ResNet18 (BasicBlock) here and load the published state_dict by URL. Layer key names match
torchvision, so the official checkpoint loads directly.
"""

import torch
import torch.nn as nn

_URL = "https://download.pytorch.org/models/resnet18-f37072fd.pth"


def conv3x3(i, o, s=1):
    return nn.Conv2d(i, o, 3, stride=s, padding=1, bias=False)


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, inp, out, stride=1, downsample=None):
        super().__init__()
        self.conv1 = conv3x3(inp, out, stride)
        self.bn1 = nn.BatchNorm2d(out)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3(out, out)
        self.bn2 = nn.BatchNorm2d(out)
        self.downsample = downsample

    def forward(self, x):
        idt = x
        y = self.relu(self.bn1(self.conv1(x)))
        y = self.bn2(self.conv2(y))
        if self.downsample is not None:
            idt = self.downsample(x)
        return self.relu(y + idt)


class ResNet18(nn.Module):
    def __init__(self):
        super().__init__()
        self.inplanes = 64
        self.conv1 = nn.Conv2d(3, 64, 7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(3, stride=2, padding=1)
        self.layer1 = self._make(64, 2)
        self.layer2 = self._make(128, 2, stride=2)
        self.layer3 = self._make(256, 2, stride=2)
        self.layer4 = self._make(512, 2, stride=2)
        self.avgpool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Linear(512, 1000)

    def _make(self, planes, blocks, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes, 1, stride=stride, bias=False),
                nn.BatchNorm2d(planes))
        layers = [BasicBlock(self.inplanes, planes, stride, downsample)]
        self.inplanes = planes
        for _ in range(1, blocks):
            layers.append(BasicBlock(planes, planes))
        return nn.Sequential(*layers)


def resnet18_pretrained(device):
    m = ResNet18()
    sd = torch.hub.load_state_dict_from_url(_URL, progress=False, map_location="cpu")
    m.load_state_dict(sd)
    return m.eval().to(device)
