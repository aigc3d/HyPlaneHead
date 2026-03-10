# SPDX-FileCopyrightText: Copyright (c) 2021-2022 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.


''' 
Core implementation of near-equal-area warping in Hy-plane representation.
Please add these functions to render.py for tri-plane-like representations.
e.g.
https://github.com/NVlabs/eg3d/blob/main/eg3d/training/volumetric_rendering/renderer.py
https://github.com/SizheAn/PanoHead/blob/main/training/volumetric_rendering/renderer.py
https://github.com/lhyfst/SphereHead/blob/main/training/volumetric_rendering/renderer.py

usage:
output_sphere_features = sample_from_sphplane(sphere_features, coordinates, mode='bilinear', padding_mode='zeros', box_warp=1, sph2cir_flag=True, cir2squ_flag=True)
'''

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

from training.volumetric_rendering.ray_marcher import MipRayMarcher2
def cartesian_to_spherical(coordinates):
    radius = (coordinates ** 2).sum(axis=-1).sqrt()
    radius = radius / math.sqrt(3)
    radius = 2.0 * radius - 1.0

    theta = torch.atan2((coordinates[:, :, :2] ** 2).sum(dim=-1).sqrt(), coordinates[:, :, 2])
    theta = theta / math.pi
    theta = 2.0 * theta - 1.0

    phi = torch.atan2(coordinates[:, :, 1], coordinates[:, :, 0])
    phi = phi / math.pi
    return theta, phi, radius

def lambert_azimuthal_equal_area_projection(psi, theta):
    R = 2 * torch.cos(psi / 2)
    Theta = -theta
    return R, Theta

def spherical_to_circle(theta, phi):
    psi = theta
    theta = phi
    r_circle, theta_circle = lambert_azimuthal_equal_area_projection(psi, theta)
    r_circle /= 2 
    return r_circle, theta_circle

def circle_polar2cartesian(r, theta):
    x = r * torch.cos(theta)
    y = r * torch.sin(theta)
    return x, y

def denormalize_theta_phi(theta, phi):
    theta = (theta + 1) * math.pi / 2
    phi = phi * math.pi
    return theta, phi

def elliptical_grid_forward(u, v):
    epsilon = 1e-8
    inner_term = u**2 - v**2 

    x = 0.5 * torch.sqrt(2 + inner_term + 2 * math.sqrt(2) * u + epsilon) - 0.5 * torch.sqrt(2 + inner_term - 2 * math.sqrt(2) * u + epsilon)
    y = 0.5 * torch.sqrt(2 - inner_term + 2 * math.sqrt(2) * v + epsilon) - 0.5 * torch.sqrt(2 - inner_term - 2 * math.sqrt(2) * v + epsilon)

    return x, y

def cir2squ_mapping(x, y):
    return elliptical_grid_forward(x,y)

def sample_from_sphplane(sphere_features, coordinates, mode='bilinear', padding_mode='zeros', box_warp=None, sph2cir_flag=False, cir2squ_flag=False):
    """
    sphere_features: the square feature map of the sphere plane, shape (batch_size, C, H, W)
    coordinates: the coordinates of all query points, shape (batch_size, N, 3)
    use near-equal-area warping: sph2cir_flag=True and cir2squ_flag=True
    use original theta-phi warping: sph2cir_flag=False and cir2squ_flag=False
    """
    bs, C, H, W = sphere_features.shape
    coordinates = (2/box_warp) * coordinates 
    theta, phi, _radius = cartesian_to_spherical(coordinates_sph)

    if sph2cir_flag:
        print('convert coordinates on the spherical plane to its corresponding coordinates on the circle plane (Lambert azimuthal equal-area projection)')
        theta_denorm, phi_denorm = denormalize_theta_phi(theta, phi)
        r_circle, theta_circle = spherical_to_circle(theta_denorm, phi_denorm)
        u_cir, v_cir = circle_polar2cartesian(r_circle, theta_circle)
        if cir2squ_flag:
            print('convert coordinates on the circle plane to its corresponding UV coordinates on the square feature map (elliptical grid mapping)')
            u_squ, v_squ = cir2squ_mapping(u_cir, v_cir)
            projected_coordinates_sph = torch.stack([u_squ, v_squ], dim=-1).unsqueeze(1)
        else:
            projected_coordinates_sph = torch.stack([u_cir, v_cir], dim=-1).unsqueeze(1)
    else:
        print('original theta-phi version')
        projected_coordinates_sph = torch.stack([theta, phi], dim=-1).unsqueeze(1)

    output_sphere_features = torch.nn.functional.grid_sample(sphere_features, projected_coordinates_sph.float(), mode=mode, padding_mode=padding_mode, align_corners=False).permute(0, 3, 2, 1).reshape(bs, 1, N, C)

    return output_sphere_features