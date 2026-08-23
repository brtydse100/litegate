# LiteGate Architecture style and overview

## 1. Minimal moving parts

Introduce no service or infrastructure component unless the feature is impossible without it. Each addition is operational surface the user must run, monitor, and keep available.

## 2. Simple deployment
Users should be able to deploy and use the product easily 

## 3. Simple of use
People who want to use LiteGate should be able to do it with minimal knowledge and understanding of the product.

## 4. Clear separation between users and man
Preserve the authorization boundary, users should only be concern about the creation of there api key
