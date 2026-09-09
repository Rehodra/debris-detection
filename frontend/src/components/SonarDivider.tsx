export default function SonarDivider({ className = "" }: { className?: string }) {
  return (
    <div className={`sonar-divider ${className}`} aria-hidden="true">
      <svg
        viewBox="0 0 1440 24"
        preserveAspectRatio="none"
        className="w-full h-full"
        fill="none"
      >
        <path
          d="M0 12 C60 4, 80 20, 120 12 C160 4, 180 20, 240 12 C300 4, 320 20, 360 12 C400 4, 420 20, 480 12 C520 4, 540 20, 600 12 C640 4, 660 20, 720 12 C760 4, 780 20, 840 12 C880 4, 900 20, 960 12 C1000 4, 1020 20, 1080 12 C1120 4, 1140 20, 1200 12 C1240 4, 1260 20, 1320 12 C1360 4, 1380 20, 1440 12"
          stroke="#1C7C72"
          strokeWidth="1.5"
          strokeOpacity="0.25"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}
