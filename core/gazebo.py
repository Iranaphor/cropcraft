import bpy
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import pprint


class GazeboModel:

    def __init__(self, path: str, name: str, author: str = None, use_absolute_path: bool = False):
        self.name = name
        self.author = author or 'Generated by cropcraft'
        self.sdf_filename = 'model.sdf'
        self.config_filename = 'model.config'
        self.use_absolute_path = use_absolute_path

        self.model_path = path
        self.meshes_path = os.path.join(self.model_path, 'meshes')
        self.materials_path = os.path.join(self.model_path, 'materials')

        os.makedirs(self.meshes_path, exist_ok=True)
        os.makedirs(self.materials_path, exist_ok=True)

        # export sdf xml based off the scene
        self.sdf = ET.Element('sdf', attrib={'version': '1.7'})

        self.model = ET.SubElement(self.sdf, "model", attrib={"name": self.name})
        ET.SubElement(self.model, "static").text = 'true'

    def make_uri(self, filepath: str):
        if self.use_absolute_path:
            return os.path.abspath(filepath)

        relpath = os.path.relpath(filepath, os.path.dirname(self.model_path))
        return f"model://{relpath}"

    def export_mesh(self, filepath: str, object: bpy.types.Object):
        ''' Exports the dae file and its associated textures of the selected objects '''
        object.select_set(True)
        bpy.ops.wm.obj_export(
            filepath=filepath + '.obj',
            check_existing=False,
            apply_modifiers=True,
            up_axis='Z',
            forward_axis='Y',
            export_selected_objects=True,
            export_materials=False,
        )
        object.select_set(False)

    def export_image(self, name: str):
        image_path = os.path.join(self.materials_path, name)

        if not os.path.exists(image_path):
            image = bpy.data.images[name]
            image.save(filepath=image_path)

    def append_ogre_material(self, name: str, material_filepath: str, image_filename: str):
        with open(material_filepath, 'w') as file:
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

    def create_sdf_material(self, visual: ET.Element, object: bpy.types.Object):
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

        material_filepath = os.path.join(self.materials_path, object.name + '.material')

        self.export_image(diffuse_map)
        self.append_ogre_material(object.name, material_filepath, diffuse_map)

        # setup diffuse/specular color
        material = ET.SubElement(visual, "material")
        script = ET.SubElement(material, 'script')
        ET.SubElement(script, 'uri').text = self.make_uri(material_filepath)
        ET.SubElement(script, 'name').text = object.name

    def create_sdf_link(self, object: bpy.types.Object):
        mesh_path = os.path.join(self.meshes_path, object.name + '.obj')

        link = ET.SubElement(self.model, "link", attrib={"name": object.name})

        visual = ET.SubElement(link, "visual", attrib={"name": object.name})
        geometry = ET.SubElement(visual, "geometry")
        mesh = ET.SubElement(geometry, "mesh")
        ET.SubElement(mesh, "uri").text = self.make_uri(mesh_path)

        self.create_sdf_material(visual, object)

        # sdf collision tags
        collision = ET.SubElement(link, "collision", attrib={"name": "collision"})
        geometry = ET.SubElement(collision, "geometry")
        mesh = ET.SubElement(geometry, "mesh")
        ET.SubElement(mesh, "uri").text = self.make_uri(mesh_path)

        surface = ET.SubElement(collision, "surface")
        contact = ET.SubElement(surface, "contact")
        ET.SubElement(contact, "collide_without_contact").text = 'true'
        ET.SubElement(contact, "collide_without_contact_bitmask").text = '0x01'
        ET.SubElement(contact, "collide_bitmask").text = '0x00'

    def create_config(self):
        model = ET.Element('model')
        name = ET.SubElement(model, 'name')
        name.text = self.name
        version = ET.SubElement(model, 'version')
        version.text = "1.0"
        sdf_tag = ET.SubElement(model, "sdf", attrib={"sdf": "1.7"})
        sdf_tag.text = self.sdf_filename

        author = ET.SubElement(model, 'author')
        name = ET.SubElement(author, 'name')
        name.text = self.author

        return model

    def add_collection(self, collection: bpy.types.Collection):
        for object in bpy.data.objects:
            object.select_set(False)

        for object in collection.all_objects.values():
            if object.type == 'MESH':
                self.export_mesh(os.path.join(self.meshes_path, object.name), object)
                self.create_sdf_link(object)

    def export_sdf(self):
        xml_string = ET.tostring(self.sdf, encoding='unicode')
        reparsed = minidom.parseString(xml_string)

        with open(os.path.join(self.model_path, self.sdf_filename), "w") as sdf_file:
            sdf_file.write(reparsed.toprettyxml(indent="  "))

    def export_config(self):
        model = self.create_config()
        xml_string = ET.tostring(model, encoding='unicode')
        reparsed = minidom.parseString(xml_string)

        config_file = open(os.path.join(self.model_path, self.config_filename), "w")
        config_file.write(reparsed.toprettyxml(indent="  "))
        config_file.close()
