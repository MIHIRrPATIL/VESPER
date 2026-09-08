import React, { ReactNode } from "react";
import { cn } from "../../lib/utils";
import BorderGlow from "./BorderGlow";

interface BentoGridProps extends React.ComponentPropsWithoutRef<"div"> {
  children: ReactNode;
  className?: string;
}

interface BentoCardProps extends React.ComponentPropsWithoutRef<"div"> {
  name: string;
  className?: string;
  background?: ReactNode;
  Icon?: React.ElementType;
  description?: string;
  href?: string;
  cta?: string;
}

const BentoGrid = ({ children, className, ...props }: BentoGridProps) => {
  return (
    <div
      className={cn("bento-grid-container", className)}
      {...props}
    >
      {children}
    </div>
  );
};

const BentoCard = ({
  name,
  className,
  background,
  Icon,
  description,
  href,
  cta,
  ...props
}: BentoCardProps) => (
  <BorderGlow
    key={name}
    className={cn("bento-card-glow-wrapper", className)}
    glowColor="0 0 100"
    colors={['#ffffff', '#ffffff', '#ffffff']}
    backgroundColor="#1C1C1C"
    borderRadius={8}
    glowRadius={12}
    glowIntensity={0.2}
    coneSpread={50}
    fillOpacity={0.02}
  >
    <div
      className="bento-card-inner"
      {...props}
    >
      <div className="bento-bg">{background}</div>
      <div className="bento-card-content">
        <div className="bento-card-top-row">
          {Icon && <Icon className="bento-icon" />}
        </div>
        <h3 className="bento-title">{name}</h3>
        <p className="bento-desc">{description}</p>
      </div>
    </div>
  </BorderGlow>
);

export { BentoCard, BentoGrid };
