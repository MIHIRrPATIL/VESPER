import * as React from "react";
import { Drawer as DrawerPrimitive } from "vaul";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Side Panel Drawer Component
 * Reference: https://21st.dev/r/coss.com/drawer (coss.com/drawer)
 * 
 * Supports multi-directional slide-in drawers (left, right, top, bottom)
 * specifically designed for side panels, diagnostics, inspector panels,
 * and command telemetry drawers.
 */

export type SidePanelDirection = "left" | "right" | "top" | "bottom";
export type SidePanelVariant = "default" | "inset" | "straight" | "headroom";

export type SidePanelDrawerProps = React.ComponentProps<typeof DrawerPrimitive.Root> & {
  direction?: SidePanelDirection;
  variant?: SidePanelVariant;
  children?: React.ReactNode;
};

export const SidePanelDrawer = ({
  direction = "right",
  shouldScaleBackground = false,
  ...props
}: SidePanelDrawerProps) => (
  <DrawerPrimitive.Root
    direction={direction}
    shouldScaleBackground={shouldScaleBackground}
    {...props}
  />
);
SidePanelDrawer.displayName = "SidePanelDrawer";

export const SidePanelTrigger = DrawerPrimitive.Trigger;
export const SidePanelPortal = DrawerPrimitive.Portal;
export const SidePanelClose = DrawerPrimitive.Close;

export const SidePanelOverlay = React.forwardRef<
  React.ElementRef<typeof DrawerPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DrawerPrimitive.Overlay
    ref={ref}
    className={cn("fixed inset-0 z-50 bg-black/70 backdrop-blur-sm transition-opacity", className)}
    {...props}
  />
));
SidePanelOverlay.displayName = DrawerPrimitive.Overlay.displayName;

interface SidePanelContentProps
  extends React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Content> {
  direction?: SidePanelDirection;
  variant?: SidePanelVariant;
}

export const SidePanelContent = React.forwardRef<
  React.ElementRef<typeof DrawerPrimitive.Content>,
  SidePanelContentProps
>(({ className, children, direction = "right", variant = "default", ...props }, ref) => {
  const directionClasses = {
    right: "fixed inset-y-0 right-0 z-50 h-full w-full max-w-md border-l border-white/10 bg-[#141414] shadow-2xl",
    left: "fixed inset-y-0 left-0 z-50 h-full w-full max-w-md border-r border-white/10 bg-[#141414] shadow-2xl",
    bottom: "fixed inset-x-0 bottom-0 z-50 mt-24 flex h-auto flex-col rounded-t-2xl border-t border-white/10 bg-[#141414] shadow-2xl",
    top: "fixed inset-x-0 top-0 z-50 mb-24 flex h-auto flex-col rounded-b-2xl border-b border-white/10 bg-[#141414] shadow-2xl",
  };

  const variantClasses = {
    default: "",
    inset: direction === "right" 
      ? "my-4 mr-4 h-[calc(100vh-2rem)] rounded-2xl border" 
      : direction === "left" 
      ? "my-4 ml-4 h-[calc(100vh-2rem)] rounded-2xl border" 
      : "m-4 rounded-2xl border",
    headroom: direction === "right"
      ? "!inset-y-auto !top-56 !bottom-auto !mr-4 !h-[calc(100vh-15.5rem)] !max-h-[620px] rounded-2xl border"
      : "my-4 mr-4 h-[calc(100vh-2rem)] rounded-2xl border",
    straight: "rounded-none",
  };

  return (
    <SidePanelPortal>
      <SidePanelOverlay />
      <DrawerPrimitive.Content
        ref={ref}
        className={cn(
          "flex flex-col text-[#E8E3DA] outline-none",
          directionClasses[direction],
          variantClasses[variant],
          className
        )}
        {...props}
      >
        {children}
      </DrawerPrimitive.Content>
    </SidePanelPortal>
  );
});
SidePanelContent.displayName = "SidePanelContent";

export const SidePanelHeader = ({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("flex items-center justify-between p-5 border-b border-white/[0.06]", className)}
    {...props}
  >
    {children}
    <SidePanelClose className="p-1 rounded-lg text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.06] transition-colors cursor-pointer">
      <X size={16} />
    </SidePanelClose>
  </div>
);
SidePanelHeader.displayName = "SidePanelHeader";

export const SidePanelTitle = React.forwardRef<
  React.ElementRef<typeof DrawerPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DrawerPrimitive.Title
    ref={ref}
    className={cn("text-base font-medium tracking-tight text-[#E8E3DA]", className)}
    {...props}
  />
));
SidePanelTitle.displayName = DrawerPrimitive.Title.displayName;

export const SidePanelDescription = React.forwardRef<
  React.ElementRef<typeof DrawerPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DrawerPrimitive.Description
    ref={ref}
    className={cn("text-xs text-[#8E8A83]", className)}
    {...props}
  />
));
SidePanelDescription.displayName = DrawerPrimitive.Description.displayName;

export const SidePanelBody = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("flex-1 overflow-y-auto p-5 space-y-4 font-mono text-xs", className)}
    {...props}
  />
);
SidePanelBody.displayName = "SidePanelBody";

export const SidePanelFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("p-4 border-t border-white/[0.06] flex items-center justify-end gap-2", className)}
    {...props}
  />
);
SidePanelFooter.displayName = "SidePanelFooter";
