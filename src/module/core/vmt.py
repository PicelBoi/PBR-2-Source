from .material import Material, MaterialMode, GameTarget
from .config import get_config, TargetRole


'''
"VertexLitGeneric"
{
	$basetexture "pbr2source_test0_albedo"
	$bumpmap "pbr2source_test0_bump"

	$envmap "env_cubemap"
	$envmaptint "[.05 .05 .05]"
	$envmapcontrast 1.0

	$phong 1
	$phongfresnelranges "[0.2 0.8 1.0]"
	$phongexponenttexture "pbr2source_test0_phongexp"
	$phongboost 1.0
}
'''

def game_envmaptint(game: GameTarget, vlg: bool) -> float:
	if game > GameTarget.V2011: return 1.0
	return .1 if vlg else .1**2.2

def game_lightscale(game: GameTarget) -> float|None:
	if game > GameTarget.V2011: return 1.0
	if game == GameTarget.VGMOD: return 1.0
	return None


def make_vmt(mat: Material) -> str:
	pbr    = MaterialMode.is_pbr(mat.mode)
	shader = MaterialMode.get_shader(mat.mode)
	vmt    = []

	texRoles = get_config().targets
	T = TargetRole

	def post(role: TargetRole):
		return texRoles[role].postfix.rsplit('.', 2)[0]

	def write(*args: str):
		l = len(vmt)
		vmt[l:l+len(args)] = args

	write(			f'{shader}\n{{',
					f'	$basetexture		"{mat.name}{post(T.Basecolor)}"',
					f'	$bumpmap			"{mat.name}{post(T.Bumpmap)}"' )

	if MaterialMode.has_alpha(mat.mode):
		write(		'	$translucent	1')

	if pbr:
		write(
					'',
					f'	$mraotexture		"{mat.name}{post(T.Mrao)}"',
					f'	$model				{int(MaterialMode.is_model(mat.mode))}' )
		
		if mat.emit:
			write(
					f'	$emissiontexture	"{mat.name}{post(T.Emit)}"')
		if mat.height:
			write(
					'',
					'	$parallax			1',
					'	$parallaxdepth		0.04',
					'	$parallaxcenter		0.5')

	else:
		envmaptint = game_envmaptint(mat.target, MaterialMode.is_vlg(mat.mode))
		lightscale = game_lightscale(mat.target)

		# Do we use envmaps?
		if MaterialMode.has_envmap(mat.mode):
			write(
					'',
					f'	$envmap						"env_cubemap"',
					f'	$envmaptint					"[{envmaptint} {envmaptint} {envmaptint}]"',
					'	$envmapcontrast				1.0' )


			write(
			'	$basetextureenvmapmask		1')
				
				# Enable fresnel for envmap always
			if MaterialMode.is_vlg(mat.mode): write(
				f'	$envmapfresnel				1')
			else: write(
				f'	$fresnelreflection			0')

			# Does the game support lightscale?
			if lightscale:
				write(
						f'	$envmaplightscale			{lightscale}' )

		# Add Dark Detail to allow phong albedo tinting without the metalness darkining affecting the specular itself
		write(
			'',
			f'	$detail		"{mat.name}{post(T.MtlDarken)}"',
			'	$detailscale	1',
			'	$detailblendmode	2'
		)




		# Phong base
		if MaterialMode.has_phong(mat.mode):
			write(
					'',
					'	$phong 1',
					f'	$phongexponenttexture		"{mat.name}{post(T.PhongExp)}"',
					'	$phongboost					5')
		
		# Are envmap or phong using the fresnel ranges?
		if MaterialMode.has_phong(mat.mode) or MaterialMode.has_envmap(mat.mode):
			write(	'	$phongfresnelranges			"[1 7.5 15]"')


		# Do we need to handle self-illumination?
		if MaterialMode.has_selfillum(mat.mode):
			write(	'',
					'	$EmissiveBlendEnabled 		1',
					'	$EmissiveBlendStrength 		1',
					'	$EmissiveBlendTexture 		vgui/white',
					f'	$EmissiveBlendBaseTexture	"{mat.name}{post(T.Emit)}"',
					'	$EmissiveBlendTint 			" [ 1 1 1 ] "',
					'	$EmissiveBlendScrollVector 	" [ 0 0 ] "',)

		# Do we need to handle self-illumination on brushes?
		if MaterialMode.has_lg_selfillum(mat.mode):
			write(	'',
					'$selfillummask	"{mat.name}{post(T.Emit)}"')
		# Add rim lighting
		write(
				'',
				'	$rimlight				1',
				'	$rimlightexponent		2',
				'	$rimlightboost			1',
				'	$rimlightmask			1'
		)
	write('}')
	return '\n'.join(vmt)
