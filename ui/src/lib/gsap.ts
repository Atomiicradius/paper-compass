import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

// The one place where GSAP is configured. Every motion component imports gsap and ScrollTrigger from here.
gsap.registerPlugin(ScrollTrigger);

export { gsap, ScrollTrigger };
