import bpy
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os


def export_mesh(filepath: str):
    ''' Exports the dae file and its associated textures of the selected objects '''
    bpy.ops.wm.obj_export(
        filepath=filepath + '.obj',
        check_existing=False,
        apply_modifiers=True,
        up_axis='Z',
        forward_axis='X',
        export_selected_objects=True,
        export_materials=True,
    )


def export_image(name: str, dirname: str):
    image_path = os.path.join(dirname, name)

    if not os.path.exists(image_path):
        image = bpy.data.images[name]
        image.save(filepath=image_path)


def append_ogre_material(name: str, material_filepath: str, image_filename: str):
    with open(material_filepath, 'a') as file:
        file.write(f'''\
material {name}
{{
  technique
  {{
    pass
    {{
      cull_hardware none
      cull_software none

      texture_unit
      {{
        texture {image_filename}
      }}
    }}
  }}
}}

''')


def create_sdf_material(visual: ET.Element, object: bpy.types.Object, filepath: str):
    # grab diffuse/albedo map
    diffuse_map = None
    if object.active_material and object.active_material.node_tree:
        nodes = object.active_material.node_tree.nodes
        principled = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
        if principled is not None:
            base_color = principled.inputs['Base Color']  # Or principled.inputs[0]
            if len(base_color.links):
                link_node = base_color.links[0].from_node
                diffuse_map = link_node.image.name

    material_filepath = os.path.join(filepath, object.name + '.material')

    export_image(diffuse_map, filepath)
    append_ogre_material(object.name, material_filepath, diffuse_map)

    # setup diffuse/specular color
    material = ET.SubElement(visual, "material")
    script = ET.SubElement(material, 'script')
    ET.SubElement(script, 'uri').text = material_filepath
    ET.SubElement(script, 'name').text = object.name


def create_sdf_link(
    model: ET.Element,
    object: bpy.types.Object,
    meshes_path: str,
    material_path: str,
):
    mesh_uri = os.path.join(meshes_path, object.name + '.obj')

    link = ET.SubElement(model, "link", attrib={"name": object.name})

    visual = ET.SubElement(link, "visual", attrib={"name": object.name})
    geometry = ET.SubElement(visual, "geometry")
    mesh = ET.SubElement(geometry, "mesh")
    ET.SubElement(mesh, "uri").text = mesh_uri

    create_sdf_material(visual, object, material_path)

    # sdf collision tags
    collision = ET.SubElement(link, "collision", attrib={"name": "collision"})
    geometry = ET.SubElement(collision, "geometry")
    mesh = ET.SubElement(geometry, "mesh")
    ET.SubElement(mesh, "uri").text = mesh_uri

    surface = ET.SubElement(collision, "surface")
    contact = ET.SubElement(surface, "contact")
    ET.SubElement(contact, "collide_without_contact").text = 'true'
    ET.SubElement(contact, "collide_without_contact_bitmask").text = '0x01'
    ET.SubElement(contact, "collide_bitmask").text = '0x00'


def create_config(model_name: str, sdf_filename: str, author_name: str):
    model = ET.Element('model')
    name = ET.SubElement(model, 'name')
    name.text = model_name
    version = ET.SubElement(model, 'version')
    version.text = "1.0"
    sdf_tag = ET.SubElement(model, "sdf", attrib={"sdf": "1.8"})
    sdf_tag.text = sdf_filename

    author = ET.SubElement(model, 'author')
    name = ET.SubElement(author, 'name')
    name.text = author_name

    return model


def export_sdf(path: str, name: str, collection: bpy.types.Collection, author: str = None):
    sdf_filename = 'model.sdf'
    model_config_filename = 'model.config'
    meshes_path = os.path.join(path, 'meshes')
    materials_path = os.path.join(path, 'materials')

    os.makedirs(meshes_path, exist_ok=True)
    os.makedirs(materials_path, exist_ok=True)

    if not author:
        author = 'Generated by cropcraft'

    # export sdf xml based off the scene
    sdf = ET.Element('sdf', attrib={'version': '1.7'})

    model = ET.SubElement(sdf, "model", attrib={"name": name})
    ET.SubElement(model, "static").text = 'true'

    for object in collection.all_objects.values():
        if object.type == 'MESH':
            bpy.ops.object.select_all(action='DESELECT')
            object.select_set(True)
            export_mesh(os.path.join(meshes_path, object.name))
            create_sdf_link(model, object, meshes_path, materials_path)

    # sdf write to file
    xml_string = ET.tostring(sdf, encoding='unicode')
    reparsed = minidom.parseString(xml_string)

    with open(os.path.join(path, sdf_filename), "w") as sdf_file:
        sdf_file.write(reparsed.toprettyxml(indent="  "))

    # create config file
    model = create_config(name, sdf_filename, author)
    xml_string = ET.tostring(model, encoding='unicode')
    reparsed = minidom.parseString(xml_string)

    config_file = open(os.path.join(path, model_config_filename), "w")
    config_file.write(reparsed.toprettyxml(indent="  "))
    config_file.close()
