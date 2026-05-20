import React from 'react';
import { Box, type BoxProps } from '@chakra-ui/react';

export default function HeaderBrandMark(props: BoxProps) {
  return (
    <Box
      as="svg"
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      shapeRendering="geometricPrecision"
      {...props}
    >
      <circle
        cx="16"
        cy="16"
        r="10.5"
        stroke="#83F0E1"
        strokeWidth="2.75"
      />
      <path
        d="M16 5.9V8.5"
        stroke="#83F0E1"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M21.9 10.1L17.9 19.3C17.7 19.8 17.1 20 16.7 19.6L12.4 15.3C12 14.9 12.2 14.3 12.7 14.1L21.9 10.1Z"
        fill="#0F766E"
      />
      <path
        d="M10.1 21.9L14.1 12.7C14.3 12.2 14.9 12 15.3 12.4L19.6 16.7C20 17.1 19.8 17.7 19.3 17.9L10.1 21.9Z"
        fill="#83F0E1"
      />
      <circle cx="16" cy="16" r="2.15" fill="#F8FAFC" />
    </Box>
  );
}
