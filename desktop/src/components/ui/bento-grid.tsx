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
  headerRight?: ReactNode;
  href?: string;
  cta?: string;
  children?: ReactNode;
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
  headerRight,
  href,
  cta,
  children,
  ...props
}: BentoCardProps) => (
  <BorderGlow
    key={name}
    className={cn("bento-card-glow-wrapper", className)}
    glowColor="0 0 100"
    colors={['#ffffff', '#ffffff', '#ffffff']}
    backgroundColor="#1C1C1C"
    borderRadius={10}
    glowRadius={12}
    glowIntensity={0.15}
    coneSpread={50}
    fillOpacity={0.02}
  >
    <div
      className="bento-card-inner !p-5 flex flex-col justify-between h-full"
      {...props}
    >
      <div className="bento-bg">{background}</div>
      <div className="bento-card-content flex flex-col gap-2 h-full">
        <div className="bento-card-top-row flex items-center justify-between w-full mb-1">
          <div className="flex items-center gap-2.5">
            {Icon && (
              <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-white/[0.06] border border-white/[0.10] text-[#E8E3DA] shrink-0">
                <Icon size={18} strokeWidth={2.0} />
              </div>
            )}
            <h3 className="bento-title !text-[17px] font-sans font-bold text-[#E8E3DA] tracking-tight">{name}</h3>
          </div>
          {headerRight}
        </div>
        {description && <p className="bento-desc !text-[13px] text-[#A1A1AA] font-sans leading-relaxed">{description}</p>}
        {children && <div className="mt-2.5 flex-1 flex flex-col justify-start">{children}</div>}
      </div>
    </div>
  </BorderGlow>
);

export { BentoCard, BentoGrid };
