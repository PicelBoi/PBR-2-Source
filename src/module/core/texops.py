from typing import Literal
from .io.image import Image
from .material import Material, MaterialMode, NormalType
import numpy as np
import time

'''
References:
- https://marmoset.co/posts/pbr-texture-conversion/
- https://cgobsession.com/complete-guide-to-texture-map-types/
'''

'''
	basetexture   = (1 - ((1-roughness) * metallic)) * albedo
	envmapmask    = (metallic * 0.75 + 0.25) * ((1-roughness)^5)
	phongexponent = (0.8 / (roughness^3)) # it is assumed that $phongexponent = 1
	phongmask     = ((1-roughness)^5.4) * 2
'''

def normalize(img: Image, size: tuple[int, int]|None=None, mode: Literal['L', 'RGB', 'RGBA']|None=None, noAlpha: bool=False):
	''' Normalizes an input image to function with other operations. '''

	# All of this code is necessary to ensure that PIL imports work,
	# but I do not yet know if the same issues apply to imageio.

	# if img.mode == 'I':
	# 	img_bytes = img.tobytes()

	# 	arr = np.frombuffer( img_bytes, dtype=np.int32 ).astype( np.float32 )
	# 	arr /= 256

	# 	out_bytes = arr.astype( np.uint8 )
	# 	img = PIL.Image.frombytes( 'L', img.size, out_bytes.tobytes() )

	# elif img.mode == 'P':
	# 	img = img.convert( 'RGB' )

	if size:
		img = img.resize(size)

	img = img.convert(np.float32)

	if mode:
		img = img.normalize(mode)
	elif noAlpha and img.channels == 4:
		img = img.normalize('RGB')

	return img

def make_phong_exponent(mat: Material) -> Image:
	''' Generates an RGB phong exponent texture. '''

	# "The Phong exponent texture [...] red channel defines the Phong exponent value and the green for albedo tinting.
	# [...] albedo tinting is a "work in progress" feature and currently un-supported in the current shader in some branches."

	assert mat.roughness != None
	
	exponent_r = mat.roughness.copy().clip(0.05, 1).pow(-2).mult(0.8)
	exponent_g = Image.blank(mat.size, color=(0,))
	exponent_b = Image.blank(mat.size, color=(0,))
	exponent = Image.merge((exponent_r, exponent_g, exponent_b))
	
	# return exponent
	return exponent_r


def make_phong_mask(mat: Material) -> Image:
	''' Generates a L phong mask texture. '''

	assert mat.roughness != None

	mask = mat.roughness.copy().invert().pow(3).mult(1.1)
	if mat.ao: mask.mult(mat.ao)

	return mask


def make_envmask(mat: Material) -> Image:
	''' Creates an envmapmask texture from a material. '''

	assert mat.metallic != None

	# Ignore this.
	'''
	for row in enumerate(mat.roughness.data):
		for column in enumerate(row[1]):
			# Somewhere like 0.225 and below envmap is slightly blurry to clearly visible.
			if column[1][0] <= 0.225:
				# 0.05 is similar to the actual multiplied color for Blender's Environment Textures on Principled BSDF.
				envmask.data[row[0]][column[0]] = [0.05]
				print("Pixel is under 0.225")
			elif column[1][0] <= 0.3 and column[1][0] > 0.225:
				# Try to darken 0.05 til 0 (0.3)
				calculated_color = (column[1] - 0.225) * (1 / 0.075) * 0.05
				envmask.data[row[0]][column[0]] = [calculated_color]
				print("Pixel is between 0.225 (57) and 0.3 (77).")
			else:
				# Set it to black.
				envmask.data[row[0]][column[0]] = [0]
				print("Pixel blacked out")
	'''

	# Metalness time. Assume Envmapping is enabled on Metallic textures.
	envmask = mat.albedo.copy().mult(mat.metallic)

	envmask = Image(envmask.get_channel(0))

	return envmask


def make_basecolor(mat: Material) -> Image:
	''' Creates a basetexture from a material. '''

	assert mat.metallic != None
	assert mat.roughness != None
	assert mat.albedo != None

	basetexture = mat.albedo.copy()

	# Do nothing when converting to PBR
	if MaterialMode.is_pbr(mat.mode):
		if not basetexture.has_transparency():
			return basetexture.normalize('RGB')
		return basetexture

	# Convert mask to an RGBA image to avoid multiplying the alpha
	mask_alpha = Image.blank(mask.size, (1,))
	mask = Image.merge((mask, mask, mask, mask_alpha))
	basetexture.mult(mask)
	
	# Basetexture already contains alpha, don't embed masks
	if MaterialMode.has_alpha(mat.mode):
		return basetexture
	
	(r, g, b) = basetexture.split()[:3]

	# Do we need to embed the phong mask instead of envmap mask?
	using_phong = Material.swap_phong_envmap(mat)

	# Phong mask as basetexture alpha
	if using_phong and MaterialMode.has_phong(mat.mode):
		# TODO: See below
		phongmask = make_phong_mask(mat)
		phongmask.data = phongmask.data.clip(min=(1 / 255))
		return Image.merge((r, g, b, phongmask))

	# Envmap mask as basetexture alpha
	elif not using_phong and MaterialMode.embed_envmap(mat.mode):
		# TODO: This sucks, but srctools has forced my hand. Libsquish needs a flag to account for full-alpha, which we can't give it.
		# TODO: Verify that this is still an issue with sourcepp bcenc?
		envmask = make_envmask(mat)
		envmask.data = envmask.data.clip(min=(1 / 255))
		return Image.merge((r, g, b, envmask))

	# No alpha - remove the channel so we can use DXT1.
	return Image.merge((r, g, b))


def make_bumpmap(mat: Material) -> Image:
	''' Generates a RGB/RGBA bumpmap with embedded phong information when applicable. '''

	(r, g, b) = mat.normal.split()
	if mat.normalType == NormalType.GL: g.invert()

	# If using PBR, then we don't need to worry about phong.
	if MaterialMode.is_pbr(mat.mode):
		if not mat.height: return mat.normal
		return Image.merge((r, g, b, mat.height))

	# Do we need to embed the envmap mask instead of phong mask?
	if Material.swap_phong_envmap(mat):
		if MaterialMode.embed_envmap(mat.mode):
			envmask = make_envmask(mat)
			return Image.merge((r, g, b, envmask))
	else:
		if MaterialMode.has_phong(mat.mode):
			phongmask = make_phong_mask(mat)
			return Image.merge((r, g, b, phongmask))

	return Image.merge((r, g, b))


def make_mrao(mat: Material) -> Image:
	''' Generates a RGB MRAO texture. '''

	ao = mat.ao or Image.blank(mat.size, color=(1,))
	return Image.merge((mat.metallic, mat.roughness, ao))


def make_emit(mat: Material) -> Image:
	''' Gamma-corrects the emission map if necessary to match Strata PBR. '''

	assert mat.emit != None

	if MaterialMode.is_pbr(mat.mode): return mat.emit
	return mat.emit.pow(2.2)
