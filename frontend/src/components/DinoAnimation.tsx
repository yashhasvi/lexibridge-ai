import { Suspense, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Center, Environment, Html, OrbitControls, useGLTF } from "@react-three/drei";

const MODEL_PATH = "/models/sino_baby.glb";

const DinoModel = () => {
  const { scene } = useGLTF(MODEL_PATH);

  const clonedScene = useMemo(() => scene.clone(), [scene]);

  return (
    <Center top>
      <primitive object={clonedScene} scale={0.18} />
    </Center>
  );
};

useGLTF.preload(MODEL_PATH);

interface DinoAnimationProps {
  variant?: "panel" | "viewer";
  onHatch?: () => void;
}

export const DinoAnimation = ({ variant = "panel", onHatch }: DinoAnimationProps) => {
  const [hasHovered, setHasHovered] = useState(false);

  const canvasClass =
    variant === "viewer" ? "dino-canvas dino-canvas--viewer" : "dino-canvas";

  const handlePointerEnter = () => {
    if (!hasHovered) {
      setHasHovered(true);
    }
  };

  if (!hasHovered) {
    return (
      <div
        className={`${canvasClass} dino-canvas--pending`}
        onPointerEnter={handlePointerEnter}
        role="button"
        tabIndex={0}
        aria-label="Hover to hatch Pebble"
      >
        <div className="dino-loader">Hover to hatch Pebble</div>
      </div>
    );
  }

  return (
    <div className={canvasClass} aria-label="Baby dinosaur 3D preview">
      <Canvas
        shadows
        camera={{ position: [1.5, 1.6, 5.2], fov: 45 }}
        onClick={onHatch}
      >
        <color attach="background" args={["#f5fbf4"]} />
        <ambientLight intensity={0.8} />
        <directionalLight position={[5, 5, 5]} intensity={1} castShadow />
        <directionalLight position={[-5, 3, -2]} intensity={0.35} />

        <Suspense
          fallback={
            <Html center>
              <div className="dino-loader">Pebble is warming up...</div>
            </Html>
          }
        >
          <DinoModel />
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.2, 0]} receiveShadow>
            <circleGeometry args={[2.5, 64]} />
            <meshStandardMaterial color="#d9f2d0" />
          </mesh>
          <Environment preset="sunset" />
          <OrbitControls
            enablePan={false}
            minDistance={2}
            maxDistance={6}
            enableDamping
            target={[0, 0.4, 0]}
          />
        </Suspense>
      </Canvas>
    </div>
  );
};
