import React, { useEffect, useRef } from "react";
import { Animated, ViewStyle } from "react-native";

interface CascadeViewProps {
  children: React.ReactNode;
  index?: number;
  delay?: number;
  style?: ViewStyle | ViewStyle[];
}

export const CascadeView: React.FC<CascadeViewProps> = ({
  children,
  index = 0,
  delay,
  style,
}) => {
  const animValue = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const calculatedDelay = delay !== undefined ? delay : index * 60;
    animValue.setValue(0);
    const timeout = setTimeout(() => {
      Animated.timing(animValue, {
        toValue: 1,
        duration: 320,
        useNativeDriver: true,
      }).start();
    }, calculatedDelay);

    return () => clearTimeout(timeout);
  }, [index, delay]);

  const translateY = animValue.interpolate({
    inputRange: [0, 1],
    outputRange: [14, 0],
  });

  return (
    <Animated.View
      style={[
        style,
        {
          opacity: animValue,
          transform: [{ translateY }],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
};
