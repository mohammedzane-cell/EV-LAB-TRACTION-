// EV-LAB · 3D laboratory scene. Draws what the bridge (scene3d_bridge.SceneBridge) gives it:
// part meshes from core.scene3d, explosion, visibility, colours, angles and power-flow markers.
// No physics in this file: every number comes from Python (core).
import QtQuick
import QtQuick3D
import QtQuick3D.Helpers

Item {
    id: root
    objectName: "lab3dRoot"

    function angleFor(spin) {
        if (spin === "motor") return bridge.angleMotor
        if (spin === "intermediate") return bridge.angleIntermediate
        if (spin === "wheel") return bridge.angleWheel
        return 0
    }

    // camera presets: orbit angles (deg) and distance in scene radii
    function setView(preset) {
        orbit.position = Qt.vector3d(bridge.centre[0], bridge.centre[1], bridge.centre[2])
        var d = bridge.radius * 3.0
        if (preset === "front") orbit.eulerRotation = Qt.vector3d(0, 0, 0)
        else if (preset === "side") orbit.eulerRotation = Qt.vector3d(0, 90, 0)
        else if (preset === "top") orbit.eulerRotation = Qt.vector3d(-89, 0, 0)
        else if (bridge.scene === "powertrain") orbit.eulerRotation = Qt.vector3d(-24, 35, 0)
        else orbit.eulerRotation = Qt.vector3d(-18, 62, 0)
        cam.position = Qt.vector3d(0, 0, d)
        cam.eulerRotation = Qt.vector3d(0, 0, 0)
    }

    Rectangle { anchors.fill: parent; color: bridge.theme.background }

    View3D {
        id: view
        objectName: "view3d"
        anchors.fill: parent
        camera: cam
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: bridge.theme.background
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.Medium
        }

        Node {
            id: orbit
            objectName: "orbit"
            eulerRotation: Qt.vector3d(-20, 42, 0)
            PerspectiveCamera {
                id: cam
                objectName: "camera"
                z: 900
                fieldOfView: 32
                clipNear: 5
                clipFar: 80000
                // head light: follows the camera
                DirectionalLight { brightness: 0.9; ambientColor: Qt.rgba(0.22, 0.23, 0.25, 1.0) }
            }
        }
        DirectionalLight { eulerRotation: Qt.vector3d(-55, 25, 0); brightness: 1.0 }
        DirectionalLight { eulerRotation: Qt.vector3d(25, -150, 0); brightness: 0.35 }

        Model {  // ground of the vehicle scene
            visible: bridge.scene === "powertrain"
            source: "#Rectangle"
            eulerRotation.x: -90
            position: Qt.vector3d(0, -1, 0)
            scale: Qt.vector3d(50, 50, 1)
            pickable: false
            materials: PrincipledMaterial { baseColor: bridge.theme.ground; roughness: 1.0; metalness: 0.0 }
        }

        Repeater3D {
            id: partRepeater
            model: bridge.parts
            delegate: Node {
                id: holder
                required property var modelData
                property string partKey: modelData.key
                objectName: "holder_" + partKey
                visible: bridge.visibleGroups[modelData.group] !== false
                position: Qt.vector3d(modelData.origin[0] + modelData.explode[0] * bridge.explode,
                                      modelData.origin[1] + modelData.explode[1] * bridge.explode,
                                      modelData.origin[2] + modelData.explode[2] * bridge.explode)
                eulerRotation: modelData.spin === "" ? Qt.vector3d(0, 0, 0)
                             : (modelData.axis === "x" ? Qt.vector3d(root.angleFor(modelData.spin), 0, 0)
                                                        : Qt.vector3d(0, 0, root.angleFor(modelData.spin)))
                Model {
                    objectName: "part_" + holder.partKey
                    property string partKey: holder.partKey
                    geometry: bridge.geometry(holder.partKey)
                    pickable: true
                    // the SOC column: its height is the battery SOC (core.battery via the playback)
                    scale: holder.partKey === "battery_soc" ? Qt.vector3d(1, Math.max(bridge.soc, 0.005), 1)
                                                            : Qt.vector3d(1, 1, 1)
                    materials: PrincipledMaterial {
                        property var look: bridge.materials[holder.modelData.material]
                        baseColor: look.color
                        metalness: look.metalness
                        roughness: look.roughness
                        opacity: look.opacity
                        alphaMode: look.opacity < 1 ? PrincipledMaterial.Blend : PrincipledMaterial.Opaque
                        cullMode: look.opacity < 1 ? Material.NoCulling : Material.BackFaceCulling
                        emissiveFactor: bridge.selected === holder.partKey ? Qt.vector3d(0.05, 0.42, 0.50)
                                                                           : Qt.vector3d(0, 0, 0)
                    }
                }
            }
        }

        Repeater3D {  // power-flow markers (powertrain scene, during playback)
            model: bridge.particles
            delegate: Model {
                required property var modelData
                source: "#Sphere"
                pickable: false
                position: Qt.vector3d(modelData.pos[0], modelData.pos[1], modelData.pos[2])
                scale: Qt.vector3d(0.24, 0.24, 0.24)
                materials: PrincipledMaterial { baseColor: modelData.color; lighting: PrincipledMaterial.NoLighting }
            }
        }
    }

    OrbitCameraController {
        id: controller
        anchors.fill: parent
        origin: orbit
        camera: cam
        panEnabled: true
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: function(ep) {
            var r = view.pick(ep.position.x, ep.position.y)
            bridge.pick(r.objectHit ? r.objectHit.partKey : "")
        }
    }

    // labels: projected anchors (re-evaluated when the camera, the view or the explosion changes)
    property real cameraTick: cam.scenePosition.x + cam.scenePosition.y + cam.scenePosition.z
                              + orbit.eulerRotation.x + orbit.eulerRotation.y + view.width + view.height
    Repeater {
        model: bridge.labels
        delegate: Item {
            id: tag
            required property var modelData
            property bool shown: ((bridge.labelsVisible && modelData.main) || bridge.selected === modelData.key)
                                 && bridge.visibleGroups[modelData.group] !== false
            property vector3d at: {
                root.cameraTick
                return view.mapFrom3DScene(Qt.vector3d(modelData.anchor[0] + modelData.explode[0] * bridge.explode,
                                                       modelData.anchor[1] + modelData.explode[1] * bridge.explode,
                                                       modelData.anchor[2] + modelData.explode[2] * bridge.explode))
            }
            visible: shown && at.z > 0 && at.x > 0 && at.y > 0 && at.x < root.width && at.y < root.height
            x: at.x
            y: at.y
            Rectangle { width: 6; height: 6; radius: 3; x: -3; y: -3; color: bridge.theme.accent }
            Rectangle {
                x: 8; y: -box.height - 4
                width: box.width + 12; height: box.height + 6
                radius: 3
                color: bridge.theme.card
                opacity: 0.92
                border.width: 1
                border.color: bridge.selected === tag.modelData.key ? bridge.theme.accent : bridge.theme.border
                Text {
                    id: box
                    x: 6; y: 3
                    text: tag.modelData.text
                    color: bridge.theme.text
                    font.pixelSize: 11
                    font.bold: bridge.selected === tag.modelData.key
                }
            }
        }
    }

    Connections {
        target: bridge
        function onCameraRequested(preset) { root.setView(preset) }
        function onPartsChanged() { root.setView("iso") }
    }
    Component.onCompleted: setView("iso")
}
