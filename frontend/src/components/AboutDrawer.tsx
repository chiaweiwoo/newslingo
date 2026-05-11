import React from 'react';
import {
  Drawer, DrawerBody, DrawerHeader, DrawerOverlay, DrawerContent,
  DrawerCloseButton, Box, Text, VStack, HStack, Divider,
} from '@chakra-ui/react';

interface Props {
  isOpen:  boolean;
  onClose: () => void;
}

export default function AboutDrawer({ isOpen, onClose }: Props) {
  return (
    <Drawer isOpen={isOpen} placement="bottom" onClose={onClose}>
      <DrawerOverlay />
      <DrawerContent maxH="80vh" borderTopRadius="lg" bg="brand.paper">
        <DrawerCloseButton color="brand.muted" mt={1} />

        <DrawerHeader borderBottom="1px solid" borderColor="brand.rule" pb={3} pt={4}>
          <Text fontSize="md" fontWeight="700" color="brand.ink" lineHeight="1.2"
            fontFamily="'Noto Serif SC', 'Georgia', serif">
            NewsLingo
          </Text>
          <Text fontSize="xs" color="brand.muted" fontWeight="400" mt={0.5}>
            Bilingual news for language learners.
          </Text>
        </DrawerHeader>

        <DrawerBody py={5} overflowY="auto">
          <VStack spacing={5} align="stretch">

            <Text fontSize="sm" color="brand.ink" lineHeight="1.8">
              NewsLingo is a bilingual news reader for learning English through
              Chinese news. Headlines from{' '}
              <Text as="span" fontWeight="600">联合早报</Text> and{' '}
              <Text as="span" fontWeight="600">Astro 本地圈</Text> are translated
              by AI and organised by region — so you read news you already
              understand while picking up natural English phrasing.
            </Text>

            <Divider borderColor="brand.rule" />

            <Box>
              <Text fontSize="xs" fontWeight="700" color="brand.red"
                textTransform="uppercase" letterSpacing="wider" mb={3}>
                Sources
              </Text>
              <VStack spacing={2} align="stretch">
                <HStack justify="space-between">
                  <Text fontSize="xs" color="brand.muted">联合早报 (Zaobao)</Text>
                  <Text fontSize="xs" color="brand.ink">Singapore · International</Text>
                </HStack>
                <HStack justify="space-between">
                  <Text fontSize="xs" color="brand.muted">Astro 本地圈</Text>
                  <Text fontSize="xs" color="brand.ink">Malaysia · Singapore · International</Text>
                </HStack>
              </VStack>
            </Box>

            <Divider borderColor="brand.rule" />

            <Box>
              <Text fontSize="xs" fontWeight="700" color="brand.red"
                textTransform="uppercase" letterSpacing="wider" mb={3}>
                How It Works
              </Text>
              <VStack spacing={1.5} align="stretch">
                {[
                  'Headlines are scraped every 3 hours',
                  'Translated to English by Claude Haiku',
                  'Quality-checked by Claude Sonnet',
                  'Organised by region and date',
                ].map(step => (
                  <HStack key={step} spacing={2} align="flex-start">
                    <Text fontSize="xs" color="brand.red" flexShrink={0} mt="1px">–</Text>
                    <Text fontSize="xs" color="brand.muted" lineHeight="1.6">{step}</Text>
                  </HStack>
                ))}
              </VStack>
            </Box>

            <Divider borderColor="brand.rule" />
            <Text fontSize="2xs" color="brand.muted" textAlign="center" pb={2} lineHeight="1.6">
              Updated every 3 hours · Built with ☕ in Malaysia
            </Text>

          </VStack>
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
