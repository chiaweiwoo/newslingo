import { extendTheme } from '@chakra-ui/react';

const theme = extendTheme({
  fonts: {
    heading: `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`,
    body: `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`,
  },
  colors: {
    brand: {
      ink:    '#111111',
      paper:  '#f5f1ea',
      red:    '#c8102e',
      muted:  '#888888',
      rule:   '#e0dbd2',
    },
  },
  radii: {
    none: '0',
    sm:   '2px',
    base: '3px',
    md:   '4px',
    lg:   '6px',
    xl:   '8px',
    '2xl': '12px',
    full: '9999px',
  },
  shadows: {
    xs: '0 1px 2px rgba(0,0,0,0.05)',
    sm: '0 1px 4px rgba(0,0,0,0.08)',
  },
  styles: {
    global: {
      body: {
        bg: '#f5f1ea',
        color: '#111111',
      },
    },
  },
});

export default theme;
