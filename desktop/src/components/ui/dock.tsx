'use client';

import {
  motion,
  MotionValue,
  useMotionValue,
  useSpring,
  useTransform,
  type SpringOptions,
  AnimatePresence,
} from 'motion/react';
import {
  Children,
  cloneElement,
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { cn } from '../../lib/utils';

const DEFAULT_MAGNIFICATION = 48;
const DEFAULT_DISTANCE = 80;
const DEFAULT_PANEL_WIDTH = 58;

export type DockProps = {
  children: React.ReactNode;
  className?: string;
  distance?: number;
  panelWidth?: number;
  magnification?: number;
  spring?: SpringOptions;
};

export type DockItemProps = {
  className?: string;
  children: React.ReactNode;
  onClick?: () => void;
  ariaLabel?: string;
};

export type DockLabelProps = {
  className?: string;
  children: React.ReactNode;
};

export type DockIconProps = {
  className?: string;
  children: React.ReactNode;
};

export type DocContextType = {
  mouseY: MotionValue;
  spring: SpringOptions;
  magnification: number;
  distance: number;
};

export type DockProviderProps = {
  children: React.ReactNode;
  value: DocContextType;
};

const DockContext = createContext<DocContextType | undefined>(undefined);

function DockProvider({ children, value }: DockProviderProps) {
  return <DockContext.Provider value={value}>{children}</DockContext.Provider>;
}

function useDock() {
  const context = useContext(DockContext);
  if (!context) {
    throw new Error('useDock must be used within an DockProvider');
  }
  return context;
}

function Dock({
  children,
  className,
  spring = { mass: 0.1, stiffness: 220, damping: 18 },
  magnification = DEFAULT_MAGNIFICATION,
  distance = DEFAULT_DISTANCE,
  panelWidth = DEFAULT_PANEL_WIDTH,
}: DockProps) {
  const mouseY = useMotionValue(Infinity);
  const isHovered = useMotionValue(0);

  return (
    <div className="flex h-full items-center justify-center">
      <motion.div
        onMouseMove={({ pageY }) => {
          isHovered.set(1);
          mouseY.set(pageY);
        }}
        onMouseEnter={() => {
          isHovered.set(1);
        }}
        onMouseLeave={() => {
          isHovered.set(0);
          mouseY.set(Infinity);
        }}
        className={cn(
          'flex flex-col items-center gap-2.5 rounded-full bg-[rgba(24,24,24,0.85)] py-3 px-2 backdrop-blur-xl border border-white/10',
          className
        )}
        style={{ width: panelWidth }}
        role='toolbar'
        aria-label='Application dock'
      >
        <DockProvider value={{ mouseY, spring, distance, magnification }}>
          {children}
        </DockProvider>
      </motion.div>
    </div>
  );
}

function DockItem({ children, className, onClick, ariaLabel }: DockItemProps) {
  const ref = useRef<HTMLButtonElement>(null);
  const domRectRef = useRef<{ y: number; height: number } | null>(null);

  const { distance, magnification, mouseY, spring } = useDock();

  const isHovered = useMotionValue(0);

  const updateRect = () => {
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      domRectRef.current = { y: rect.y, height: rect.height };
    }
  };

  useEffect(() => {
    updateRect();
    window.addEventListener('resize', updateRect);
    return () => window.removeEventListener('resize', updateRect);
  }, []);

  const mouseDistance = useTransform(mouseY, (val) => {
    let rect = domRectRef.current;
    if (!rect && ref.current) {
      const r = ref.current.getBoundingClientRect();
      rect = { y: r.y, height: r.height };
      domRectRef.current = rect;
    }
    if (!rect) return Infinity;
    return val - rect.y - rect.height / 2;
  });

  const heightTransform = useTransform(
    mouseDistance,
    [-distance, 0, distance],
    [42, magnification, 42]
  );

  const height = useSpring(heightTransform, spring);

  return (
    <motion.button
      ref={ref}
      type="button"
      style={{ height, width: height }}
      onHoverStart={() => {
        updateRect();
        isHovered.set(1);
      }}
      onHoverEnd={() => isHovered.set(0)}
      onFocus={() => isHovered.set(1)}
      onBlur={() => isHovered.set(0)}
      whileTap={{ scale: 0.94 }}
      transition={{ type: 'spring', stiffness: 350, damping: 25 }}
      className={cn(
        'relative inline-flex items-center justify-center rounded-[18px] p-2 transition-all cursor-pointer outline-none focus-visible:ring-1 focus-visible:ring-white/40 border border-transparent',
        className
      )}
      role='button'
      aria-label={ariaLabel}
      onClick={onClick}
    >
      {Children.map(children, (child) =>
        cloneElement(child as React.ReactElement<any>, { height, isHovered })
      )}
    </motion.button>
  );
}

function DockLabel({ children, className, ...rest }: DockLabelProps) {
  const restProps = rest as Record<string, unknown>;
  const isHovered = restProps['isHovered'] as MotionValue<number>;
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const unsubscribe = isHovered.on('change', (latest) => {
      setIsVisible(latest === 1);
    });

    return () => unsubscribe();
  }, [isHovered]);

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, x: -6, scale: 0.95 }}
          animate={{ opacity: 1, x: 12, scale: 1 }}
          exit={{ opacity: 0, x: -6, scale: 0.95 }}
          transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
          className={cn(
            'absolute left-full top-1/2 -translate-y-1/2 ml-2 w-fit whitespace-pre rounded-lg border border-[#2C2C2C] bg-[#161616] px-2.5 py-1 text-xs font-mono font-medium text-[#E8E3DA] shadow-[0_8px_24px_rgba(0,0,0,0.6)] backdrop-blur-md pointer-events-none z-50',
            className
          )}
          role='tooltip'
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function DockIcon({ children, className, ...rest }: DockIconProps) {
  const restProps = rest as Record<string, unknown>;
  const height = restProps['height'] as MotionValue<number>;

  const iconSize = useTransform(height, (val) => Math.max(19, (val || 42) * 0.48));

  return (
    <motion.div
      style={{ height: iconSize, width: iconSize }}
      className={cn('flex items-center justify-center pointer-events-none [&>svg]:w-full [&>svg]:h-full', className)}
    >
      {children}
    </motion.div>
  );
}

export { Dock, DockIcon, DockItem, DockLabel };
